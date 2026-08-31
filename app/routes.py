from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from .analysis import sentiment_score, tokenize
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
        "city": args.get("city", "全部"),
        "status": args.get("status", "全部"),
        "start": _date_value(args.get("start")),
        "end": _date_value(args.get("end"), end=True),
        "min_price": _number_value(args.get("min_price")),
        "max_price": _number_value(args.get("max_price")),
    }


def filter_concerts(filters):
    query = ConcertInfo.query
    if filters["artist"] and filters["artist"] != "全部":
        query = query.filter(ConcertInfo.artist_name == filters["artist"])
    if filters["city"] and filters["city"] != "全部":
        query = query.filter(ConcertInfo.city == filters["city"])
    if filters["status"] and filters["status"] != "全部":
        query = query.filter(ConcertInfo.sale_status == filters["status"])
    if filters["start"]:
        query = query.filter(ConcertInfo.show_time >= filters["start"])
    if filters["end"]:
        query = query.filter(ConcertInfo.show_time <= filters["end"])
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


def _filtered_payload(filters):
    concerts = filter_concerts(filters)
    ids = {concert.id for concert in concerts}
    comments = [comment for comment in CommentInfo.query.order_by(CommentInfo.comment_time.asc()).all() if comment.concert_id in ids]

    cities = Counter(concert.city for concert in concerts)
    price_bins = Counter()
    for concert in concerts:
        price = float(concert.min_price or 0)
        bucket = "0-499" if price < 500 else "500-999" if price < 1000 else "1000-1499" if price < 1500 else "1500+"
        price_bins[bucket] += 1

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

    last_updated_values = [concert.collected_at for concert in concerts] + [comment.collected_at for comment in comments]
    last_updated = max(last_updated_values).strftime("%Y.%m.%d") if last_updated_values else "暂无"
    average_sentiment = round(total_sentiment / len(comments) * 100) if comments else 0
    return {
        "metrics": {
            "concerts": len(concerts),
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
        "concerts": [concert.to_dict() for concert in concerts],
        "comments": [comment.to_dict() for comment in comments[:6]],
        "recommendations": build_recommendations(filters, limit=4),
    }


@main.get("/")
def dashboard():
    return render_template("dashboard.html")


@main.get("/api/overview")
def overview():
    filters = request_filters()
    payload = _filtered_payload(filters)
    payload["meta"] = {
        "artists": [item[0] for item in ConcertInfo.query.with_entities(ConcertInfo.artist_name).distinct().order_by(ConcertInfo.artist_name).all()],
        "cities": [item[0] for item in ConcertInfo.query.with_entities(ConcertInfo.city).distinct().order_by(ConcertInfo.city).all()],
        "statuses": [item[0] for item in ConcertInfo.query.with_entities(ConcertInfo.sale_status).distinct().order_by(ConcertInfo.sale_status).all()],
        "source": "本地公开数据快照",
        "filters": {
            "artist": filters["artist"],
            "city": filters["city"],
            "status": filters["status"],
        },
    }
    return jsonify(payload)


@main.get("/api/recommendations")
def recommendations():
    return jsonify({"items": build_recommendations(request_filters(), limit=8)})


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


def _analytics_context():
    filters = request_filters()
    concerts = filter_concerts(filters)
    concert_ids = {concert.id for concert in concerts}
    comments = [
        comment
        for comment in CommentInfo.query.order_by(CommentInfo.comment_time.asc()).all()
        if comment.concert_id in concert_ids
    ]
    details = []
    if concert_ids:
        details = TicketPriceDetail.query.filter(TicketPriceDetail.concert_id.in_(concert_ids)).all()
    return filters, concerts, comments, details


def _analytics_response(payload):
    warnings = _filter_warnings()
    if warnings:
        payload["note"] = "；".join(warnings + ([payload["note"]] if payload.get("note") else []))
    return jsonify(payload)


@main.get("/api/analytics/map")
def analytics_map():
    _, concerts, _, _ = _analytics_context()
    return _analytics_response(map_data(concerts))


@main.get("/api/analytics/trend")
def analytics_trend():
    _, concerts, comments, _ = _analytics_context()
    return _analytics_response(trend_data(concerts, comments))


@main.get("/api/analytics/calendar")
def analytics_calendar():
    _, concerts, comments, _ = _analytics_context()
    return _analytics_response(calendar_data(concerts, comments))


@main.get("/api/analytics/prices")
def analytics_prices():
    _, concerts, comments, details = _analytics_context()
    return _analytics_response(price_data(concerts, comments, details))


@main.get("/api/analytics/topics")
def analytics_topics():
    _, _, comments, _ = _analytics_context()
    return _analytics_response(topic_data(comments))


@main.get("/api/analytics/artists")
def analytics_artists():
    _, concerts, comments, _ = _analytics_context()
    return _analytics_response(artist_data(concerts, comments))


@main.get("/api/analytics/sources")
def analytics_sources():
    _, concerts, _, _ = _analytics_context()
    return _analytics_response(sources_data(concerts))
