from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from .analysis import sentiment_score, tokenize
from .cache import cache_key, clear_cache, get_cached, set_cached
from .analytics import (
    artist_data,
    calendar_data,
    map_data,
    price_data,
    topic_data,
    trend_data,
    sources_data,
)
from .models import CommentInfo, ConcertInfo, TicketPriceDetail
from .recommend import build_recommendations
from .time_utils import utcnow


main = Blueprint("main", __name__)


def _date_value(value, end=False):
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        return parsed + timedelta(days=1) - timedelta(seconds=1) if end else parsed
    except ValueError:
        return None


def _number_value(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def request_filters():
    args = request.args
    return {
        "artist": args.get("artist", "全部"),
        "category": args.get("category", "演唱会"),
        "city": args.get("city", "全部"),
        "status": args.get("status", "全部"),
        "start": _date_value(args.get("start")),
        "end": _date_value(args.get("end"), end=True),
        "min_price": _number_value(args.get("min_price")),
        "max_price": _number_value(args.get("max_price")),
    }


def _apply_filters(query, filters):
    """把筛选条件应用到查询对象 (过滤部分, 不含价格)。"""
    if filters["artist"] and filters["artist"] != "全部":
        query = query.filter(ConcertInfo.artist_name == filters["artist"])
    if filters["category"] and filters["category"] != "全部":
        query = query.filter(ConcertInfo.category == filters["category"])
    if filters["city"] and filters["city"] != "全部":
        query = query.filter(ConcertInfo.city == filters["city"])
    if filters["status"] and filters["status"] != "全部":
        query = query.filter(ConcertInfo.sale_status == filters["status"])
    if filters["start"]:
        query = query.filter(ConcertInfo.show_time >= filters["start"])
    if filters["end"]:
        query = query.filter(ConcertInfo.show_time <= filters["end"])
    return query


def filter_concerts(filters, limit=None):
    """返回过滤后的场次对象列表 (价格过滤在 Python 侧完成)。"""
    query = _apply_filters(ConcertInfo.query, filters)
    if limit:
        query = query.limit(limit)
    filtered = []
    for concert in query.order_by(ConcertInfo.show_time.asc()).all():
        concert_min = float(concert.min_price) if concert.min_price is not None else None
        concert_max = float(concert.max_price) if concert.max_price is not None else concert_min
        if filters["min_price"] is not None and (concert_max is None or concert_max < filters["min_price"]):
            continue
        if filters["max_price"] is not None and (concert_min is None or concert_min > filters["max_price"]):
            continue
        filtered.append(concert)
    return filtered


def _filtered_payload(filters, list_limit=60):
    from sqlalchemy import func
    # 1) 轻量查询: 仅取过滤后的场次 id/城市/票价, 不物化 2 万多个 ORM 对象
    query = _apply_filters(ConcertInfo.query, filters)
    rows = (
        query.with_entities(
            ConcertInfo.id,
            ConcertInfo.city,
            ConcertInfo.min_price,
            ConcertInfo.collected_at,
            func.count(CommentInfo.id),
        )
        .outerjoin(CommentInfo, CommentInfo.concert_id == ConcertInfo.id)
        .group_by(ConcertInfo.id)
        .all()
    )
    # 价格过滤(无法下推到 SQL 的 min/max 逻辑)在元组上完成
    kept = []
    for row in rows:
        cid, city, min_price, collected_at, comments_count = row
        cmin = float(min_price) if min_price is not None else None
        cmax = cmin
        if filters["min_price"] is not None and (cmax is None or cmax < filters["min_price"]):
            continue
        if filters["max_price"] is not None and (cmin is None or cmin > filters["max_price"]):
            continue
        kept.append(row)
    ids = {r[0] for r in kept}

    # 2) 统计聚合
    cities = Counter(r[1] or "未知" for r in kept)
    price_bins = Counter()
    for r in kept:
        price = float(r[2] or 0)
        bucket = "0-499" if price < 500 else "500-999" if price < 1000 else "1000-1499" if price < 1500 else "1500+"
        price_bins[bucket] += 1
    last_dt = max((r[3] for r in kept), default=None)
    for concert in ConcertInfo.query.filter(ConcertInfo.id.in_(ids)).with_entities(ConcertInfo.collected_at).all():
        if concert[0] and (last_dt is None or concert[0] > last_dt):
            last_dt = concert[0]

    # 3) 评论采样分析 (情感/词云/地区/月趋势)
    comments = _load_comments_for_ids(ids, max_sample=1200)
    trend = Counter(comment.comment_time.strftime("%m月") for comment in comments if comment.comment_time)
    sentiment = Counter()
    regions = Counter(comment.user_region or "未提供" for comment in comments)
    keywords = Counter()
    total_sentiment = 0.0
    for comment in comments:
        score = comment.sentiment_score if comment.sentiment_score is not None else sentiment_score(comment.comment_text)
        total_sentiment += score
        sentiment["正面" if score >= 0.6 else "负面" if score <= 0.4 else "中性"] += 1
        keywords.update(tokenize(comment.comment_text))

    last_updated = last_dt.strftime("%Y.%m.%d") if last_dt else "暂无"
    average_sentiment = round(total_sentiment / len(comments) * 100) if comments else 0

    # 4) 展示列表仅截断前 list_limit 场 (避免 9MB JSON)
    list_concerts = (
        ConcertInfo.query.filter(ConcertInfo.id.in_(ids))
        .order_by(ConcertInfo.show_time.asc())
        .limit(list_limit)
        .all()
    )
    return {
        "metrics": {
            "concerts": len(kept),
            "comments": len(comments),
            "cities": len(cities),
            "sentiment": average_sentiment,
            "last_updated": last_updated,
        },
        "charts": {
            "city": [{"name": key, "value": value} for key, value in cities.most_common()],
            "price": [{"name": key, "value": price_bins.get(key, 0)} for key in ("0-499", "500-999", "1000-1499", "1500+")],
            "trend": [{"name": key, "value": trend[key]} for key in sorted(trend)],
            "sentiment": [{"name": key, "value": sentiment.get(key, 0)} for key in ("正面", "中性", "负面")],
            "region": [{"name": key, "value": value} for key, value in regions.most_common(8)],
            "keywords": [{"name": key, "value": value} for key, value in keywords.most_common(14)],
        },
        "concerts": [concert.to_dict() for concert in list_concerts],
        "comments": [comment.to_dict() for comment in comments[:6]],
        "recommendations": build_recommendations(filters, limit=4),
    }


@main.get("/")
def dashboard():
    return render_template("dashboard.html")


def _overview_meta(filters):
    category = filters.get("category", "演唱会")
    # 艺人/城市/状态列表跟随当前分类, 避免相声等非演唱会艺人进入筛选器
    base = ConcertInfo.query
    if category and category != "全部":
        base = base.filter(ConcertInfo.category == category)
    return {
        "artists": [item[0] for item in base.with_entities(ConcertInfo.artist_name).distinct().order_by(ConcertInfo.artist_name).all()],
        "categories": [item[0] for item in ConcertInfo.query.with_entities(ConcertInfo.category).distinct().order_by(ConcertInfo.category).all()],
        "cities": [item[0] for item in base.with_entities(ConcertInfo.city).distinct().order_by(ConcertInfo.city).all()],
        "statuses": [item[0] for item in base.with_entities(ConcertInfo.sale_status).distinct().order_by(ConcertInfo.sale_status).all()],
        "source": "本地公开数据快照",
        "filters": {
            "artist": filters["artist"],
            "category": filters["category"],
            "city": filters["city"],
            "status": filters["status"],
        },
    }


@main.get("/api/overview")
def overview():
    from flask import current_app
    filters = request_filters()
    key = cache_key("overview", **filters)
    cached = None if current_app.testing else get_cached(key)
    if cached is not None:
        cached["meta"] = _overview_meta(filters)
        cached["cached"] = True
        return jsonify(cached)
    payload = _filtered_payload(filters)
    payload["meta"] = _overview_meta(filters)
    set_cached(key, payload, ttl=120)
    return jsonify(payload)


@main.get("/api/recommendations")
def recommendations():
    from flask import current_app
    filters = request_filters()
    key = cache_key("recommendations", limit=8, **filters)
    cached = None if current_app.testing else get_cached(key)
    if cached is not None:
        return jsonify(cached)
    payload = {"items": build_recommendations(filters, limit=8)}
    set_cached(key, payload, ttl=120)
    return jsonify(payload)


@main.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "pulse-atlas",
        "database": "connected",
        "concerts": ConcertInfo.query.count(),
        "comments": CommentInfo.query.count(),
        "timestamp": utcnow().isoformat(),
    })


def _filter_warnings():
    """Return human-readable warnings while keeping invalid filters harmless."""
    warnings = []
    date_labels = (("start", "开始日期"), ("end", "结束日期"))
    for key, label in date_labels:
        raw = request.args.get(key)
        if raw and _date_value(raw) is None:
            warnings.append(f"{label}格式无效，已忽略")
    number_labels = (("min_price", "最低价"), ("max_price", "最高价"))
    for key, label in number_labels:
        raw = request.args.get(key)
        if raw not in (None, "") and _number_value(raw) is None:
            warnings.append(f"{label}参数无效，已忽略")
    minimum = _number_value(request.args.get("min_price"))
    maximum = _number_value(request.args.get("max_price"))
    if minimum is not None and maximum is not None and minimum > maximum:
        warnings.append("最低价不能大于最高价")
    return warnings


def _load_comments_for_ids(concert_ids, max_sample=3000):
    """按场次 ID 加载评论, 超过 max_sample 时均匀采样, 避免十万级全量遍历拖垮渲染。"""
    if not concert_ids:
        return []
    ids = list(concert_ids)
    base = CommentInfo.query.filter(CommentInfo.concert_id.in_(ids))
    # 用 LIMIT 探测总量是否超过采样上限, 避免全表 COUNT
    probe = base.with_entities(CommentInfo.id).limit(max_sample + 1).all()
    if len(probe) <= max_sample:
        return base.order_by(CommentInfo.comment_time.asc()).all()
    # 超过上限: 一次性取 id 列表后均匀抽样
    all_rows = base.with_entities(CommentInfo.id).all()
    all_ids = [row[0] for row in all_rows]
    step = max(1, len(all_ids) // max_sample)
    chosen = all_ids[::step][:max_sample]
    if chosen:
        return CommentInfo.query.filter(CommentInfo.id.in_(chosen)).all()
    return []


def _analytics_context():
    from sqlalchemy import func
    filters = request_filters()
    query = _apply_filters(ConcertInfo.query, filters)
    rows = (
        query.with_entities(
            ConcertInfo.id,
            ConcertInfo.city,
            ConcertInfo.min_price,
            ConcertInfo.max_price,
            ConcertInfo.sale_status,
            ConcertInfo.show_time,
            ConcertInfo.artist_name,
            ConcertInfo.concert_name,
            ConcertInfo.category,
            ConcertInfo.venue,
            ConcertInfo.source_url,
            ConcertInfo.collected_at,
            func.count(CommentInfo.id),
        )
        .outerjoin(CommentInfo, CommentInfo.concert_id == ConcertInfo.id)
        .group_by(ConcertInfo.id)
        .all()
    )
    kept = []
    for r in rows:
        cmin = float(r[2]) if r[2] is not None else None
        cmax = float(r[3]) if r[3] is not None else cmin
        if filters["min_price"] is not None and (cmax is None or cmax < filters["min_price"]):
            continue
        if filters["max_price"] is not None and (cmin is None or cmin > filters["max_price"]):
            continue
        kept.append(r)
    concert_ids = {r[0] for r in kept}

    # 轻量场次对象(供 analytics 读取字段): 只物化过滤后的场次
    concerts = ConcertInfo.query.filter(ConcertInfo.id.in_(concert_ids)).all() if concert_ids else []
    comments = _load_comments_for_ids(concert_ids)
    details = []
    if concert_ids:
        details = TicketPriceDetail.query.filter(TicketPriceDetail.concert_id.in_(concert_ids)).limit(200).all()
    return filters, concerts, comments, details


def _analytics_response(payload):
    warnings = _filter_warnings()
    if warnings:
        payload["note"] = "；".join(warnings + ([payload["note"]] if payload.get("note") else []))
    return jsonify(payload)


def _cacheable(endpoint, data_func, ttl=300, scope=""):
    """通用缓存包装：按筛选参数缓存聚合结果。endpoint 用于区分类型, scope 附加到 key。"""
    from flask import current_app
    filters = request_filters()
    key = cache_key(endpoint, _scope=scope, **filters)
    cached = None if current_app.testing else get_cached(key)
    if cached is not None:
        cached["cached"] = True
        return _analytics_response(cached)
    _, concerts, comments, details = _analytics_context()
    data = data_func(concerts, comments, details)
    set_cached(key, data, ttl=ttl)
    return _analytics_response(data)


@main.get("/api/analytics/map")
def analytics_map():
    return _cacheable("map", lambda c, m, d: map_data(c))


@main.get("/api/analytics/trend")
def analytics_trend():
    return _cacheable("trend", lambda c, m, d: trend_data(c, m))


@main.get("/api/analytics/calendar")
def analytics_calendar():
    return _cacheable("calendar", lambda c, m, d: calendar_data(c, m))


@main.get("/api/analytics/prices")
def analytics_prices():
    return _cacheable("prices", lambda c, m, d: price_data(c, m, d))


@main.get("/api/analytics/topics")
def analytics_topics():
    return _cacheable("topics", lambda c, m, d: topic_data(m))


@main.get("/api/analytics/artists")
def analytics_artists():
    return _cacheable("artists", lambda c, m, d: artist_data(c, m, limit=10), scope="top10")


@main.get("/api/analytics/engagement")
def analytics_engagement():
    """互动榜：按评论数/点赞数排序的场次 Top, 数据复用票价分析的 engagement。"""
    def build(c, m, d):
        data = price_data(c, m, d)
        items = data.get("engagement", [])[:10]
        return {"items": items, "note": data.get("note", "")}
    return _cacheable("engagement", build)


@main.get("/api/analytics/sources")
def analytics_sources():
    return _cacheable("sources", lambda c, m, d: sources_data(c))
