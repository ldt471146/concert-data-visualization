"""Pure aggregation helpers for the public concert analytics APIs.

The functions in this module accept model-like objects and return JSON-friendly
Python values.  They deliberately do not query the database, so the same
calculations can be exercised with small in-memory fixtures.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import mean

from .analysis import sentiment_score


# Coordinates are city-centre coordinates from the commonly used Chinese
# prefecture-level city reference.  There is intentionally no fallback: an
# unlisted city is omitted from map points and reported to the caller.
CITY_COORDINATES = {
    "北京": (116.4074, 39.9042),
    "上海": (121.4737, 31.2304),
    "天津": (117.2000, 39.1333),
    "重庆": (106.5516, 29.5630),
    "广州": (113.2644, 23.1291),
    "深圳": (114.0579, 22.5431),
    "成都": (104.0668, 30.5728),
    "杭州": (120.1551, 30.2741),
    "南京": (118.7969, 32.0603),
    "武汉": (114.3055, 30.5928),
    "西安": (108.9398, 34.3416),
    "厦门": (118.0894, 24.4798),
    "青岛": (120.3826, 36.0671),
    "苏州": (120.5853, 31.2989),
    "长沙": (112.9388, 28.2282),
    "郑州": (113.6254, 34.7466),
    "济南": (117.1201, 36.6512),
    "合肥": (117.2272, 31.8206),
    "福州": (119.2965, 26.0745),
    "南昌": (115.8582, 28.6829),
    "昆明": (102.8329, 24.8801),
    "沈阳": (123.4315, 41.8057),
    "大连": (121.6147, 38.9140),
    "哈尔滨": (126.5349, 45.8038),
    "长春": (125.3235, 43.8171),
    "石家庄": (114.5149, 38.0428),
    "太原": (112.5489, 37.8706),
    "南宁": (108.3669, 22.8170),
    "海口": (110.3312, 20.0311),
    "贵阳": (106.6302, 26.6477),
    "兰州": (103.8343, 36.0611),
    "乌鲁木齐": (87.6168, 43.8256),
    "呼和浩特": (111.7492, 40.8426),
    "宁波": (121.5440, 29.8683),
    "无锡": (120.3119, 31.4912),
    "佛山": (113.1214, 23.0215),
    "东莞": (113.7518, 23.0207),
    "珠海": (113.5767, 22.2707),
    "温州": (120.6994, 27.9943),
    "烟台": (121.4479, 37.4638),
}

TOPIC_RULES = (
    ("现场体验", ("现场", "氛围", "合唱", "情绪", "感动", "歌单", "返场", "视线", "体验")),
    ("舞台音响", ("舞台", "灯光", "舞美", "音响", "屏幕", "编曲", "声音", "清晰", "模糊")),
    ("交通场馆", ("交通", "场馆", "场地", "体育中心", "路线", "动线", "市区", "停车", "排队")),
    ("票价购票", ("票价", "价格", "票档", "购票", "买票", "开售", "售票", "位置", "贵")),
    ("服务组织", ("服务", "组织", "安排", "流程", "入场", "延迟", "工作人员", "信息")),
)
TOPIC_NAMES = tuple(name for name, _ in TOPIC_RULES) + ("其他",)


def _value(item, name, default=None):
    return getattr(item, name, default)


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                return datetime.strptime(value[:10], fmt).date()
            except ValueError:
                continue
    return None


def _empty_note(items, label):
    return f"暂无{label}数据" if not items else ""


def map_data(concerts):
    counts = Counter(_value(item, "city") for item in concerts if _value(item, "city"))
    points = []
    unknown = []
    for city, count in counts.most_common():
        coordinate = CITY_COORDINATES.get(city)
        if coordinate is None:
            unknown.append(city)
            continue
        longitude, latitude = coordinate
        points.append({"name": city, "value": count, "longitude": longitude, "latitude": latitude})
    note = _empty_note(points, "城市地图")
    if unknown:
        suffix = f"未收录坐标的城市已从地图省略：{'、'.join(unknown)}"
        note = f"{note}；{suffix}" if note else suffix
    return {"items": points, "unknown_cities": unknown, "note": note}


def trend_data(concerts, comments):
    monthly_concerts = Counter()
    monthly_comments = Counter()
    weekly_concerts = Counter()
    weekly_comments = Counter()
    for concert in concerts:
        moment = _value(concert, "show_time")
        if moment is not None:
            day = _date_value(moment)
            if day:
                monthly_concerts[day.strftime("%Y-%m")] += 1
                weekly_concerts[(day - timedelta(days=day.weekday())).isoformat()] += 1
    for comment in comments:
        moment = _value(comment, "comment_time")
        day = _date_value(moment)
        if day:
            monthly_comments[day.strftime("%Y-%m")] += 1
            weekly_comments[(day - timedelta(days=day.weekday())).isoformat()] += 1
    months = sorted(set(monthly_concerts) | set(monthly_comments))
    weeks = sorted(set(weekly_concerts) | set(weekly_comments))
    return {
        "monthly": [
            {"period": key, "concerts": monthly_concerts[key], "comments": monthly_comments[key]}
            for key in months
        ],
        "weekly": [
            {"period": key, "concerts": weekly_concerts[key], "comments": weekly_comments[key]}
            for key in weeks
        ],
        "note": _empty_note(months or weeks, "趋势"),
    }


def calendar_data(concerts, comments):
    by_day = defaultdict(lambda: {"concerts": 0, "comments": 0, "cities": set(), "artists": set()})
    for concert in concerts:
        day = _date_value(_value(concert, "show_time"))
        if day:
            item = by_day[day.isoformat()]
            item["concerts"] += 1
            city = _value(concert, "city")
            artist = _value(concert, "artist_name")
            if city:
                item["cities"].add(city)
            if artist:
                item["artists"].add(artist)
    for comment in comments:
        day = _date_value(_value(comment, "comment_time"))
        if day:
            by_day[day.isoformat()]["comments"] += 1
    items = []
    for day in sorted(by_day):
        value = by_day[day]
        items.append({
            "date": day,
            "concerts": value["concerts"],
            "comments": value["comments"],
            "cities": sorted(value["cities"]),
            "artists": sorted(value["artists"]),
        })
    return {"items": items, "note": _empty_note(items, "日历")}


def price_data(concerts, comments, price_details=()):
    details_by_concert = defaultdict(list)
    for detail in price_details or ():
        price = _number(_value(detail, "price"))
        concert_id = _value(detail, "concert_id")
        if price is not None and concert_id is not None:
            details_by_concert[concert_id].append(price)

    comment_by_concert = defaultdict(list)
    for comment in comments:
        comment_by_concert[_value(comment, "concert_id")].append(comment)

    ranges = Counter()
    city_prices = defaultdict(list)
    engagement = []
    for concert in concerts:
        concert_id = _value(concert, "id")
        prices = details_by_concert.get(concert_id, [])
        minimum = _number(_value(concert, "min_price"))
        maximum = _number(_value(concert, "max_price"))
        if prices:
            minimum = min(prices)
            maximum = max(prices)
        if minimum is not None:
            bucket = "0-499" if minimum < 500 else "500-999" if minimum < 1000 else "1000-1499" if minimum < 1500 else "1500+"
            ranges[bucket] += 1
            city = _value(concert, "city")
            if city:
                city_prices[city].append(minimum)
            linked = comment_by_concert.get(concert_id, [])
            engagement.append({
                "concert_id": concert_id,
                "concert_name": _value(concert, "concert_name", ""),
                "city": city,
                "min_price": minimum,
                "max_price": maximum,
                "comments": len(linked),
                "likes": sum(_number(_value(comment, "like_count")) or 0 for comment in linked),
            })

    city_comparison = [
        {"city": city, "concerts": len(values), "average_min_price": round(mean(values), 2)}
        for city, values in sorted(city_prices.items())
    ]
    engagement.sort(key=lambda item: (-item["likes"], -item["comments"], item["min_price"]))
    return {
        "ranges": ([{"range": key, "concerts": ranges.get(key, 0)} for key in ("0-499", "500-999", "1000-1499", "1500+")] if engagement else []),
        "cities": city_comparison,
        "engagement": engagement,
        "note": _empty_note(engagement, "票价"),
    }


def topic_data(comments):
    counts = Counter()
    keyword_counts = {name: Counter() for name in TOPIC_NAMES}
    for comment in comments:
        text = str(_value(comment, "comment_text", "") or "")
        matched = False
        for name, keywords in TOPIC_RULES:
            found = [keyword for keyword in keywords if keyword in text]
            if found:
                matched = True
                counts[name] += 1
                keyword_counts[name].update(found)
        if not matched:
            counts["其他"] += 1
            keyword_counts["其他"]["其他"] += 1
    items = [
        {"topic": name, "comments": counts.get(name, 0), "keywords": dict(keyword_counts[name].most_common())}
        for name in TOPIC_NAMES
    ] if comments else []
    return {
        "items": items,
        "rules": {name: list(keywords) for name, keywords in TOPIC_RULES},
        "note": _empty_note(comments, "评论主题"),
    }


def _average_sentiment(comments):
    scores = []
    for comment in comments:
        value = _number(_value(comment, "sentiment_score"))
        if value is None:
            value = sentiment_score(str(_value(comment, "comment_text", "") or ""))
        if value is not None:
            scores.append(value)
    return round(mean(scores), 4) if scores else None


def artist_data(concerts, comments, limit=50):
    """艺人对比/热度榜。

    limit 用于限制返回条数：热度榜场景只需 Top N。综合热度 = 场次 * 3 + 评论 * 2 + 点赞折算，
    便于横向比较「哪个艺人更受关注」。
    """
    by_artist = defaultdict(list)
    comments_by_concert = defaultdict(list)
    for comment in comments:
        comments_by_concert[_value(comment, "concert_id")].append(comment)
    for concert in concerts:
        by_artist[_value(concert, "artist_name", "未提供")].append(concert)

    items = []
    for artist, artist_concerts in by_artist.items():
        linked = [comment for concert in artist_concerts for comment in comments_by_concert.get(_value(concert, "id"), [])]
        prices = [_number(_value(concert, "min_price")) for concert in artist_concerts]
        prices = [price for price in prices if price is not None]
        comment_count = len(linked)
        like_count = sum(_number(_value(comment, "like_count")) or 0 for comment in linked)
        items.append({
            "artist": artist,
            "concerts": len(artist_concerts),
            "cities": len({_value(concert, "city") for concert in artist_concerts if _value(concert, "city")}),
            "average_min_price": round(mean(prices), 2) if prices else None,
            "comments": comment_count,
            "likes": like_count,
            "average_sentiment": _average_sentiment(linked),
            "heat": round(len(artist_concerts) * 3 + comment_count * 2 + min(like_count, 1000000) / 20000, 1),
        })
    items.sort(key=lambda item: (-item["heat"], item["artist"]))
    if limit:
        items = items[:limit]
    return {
        "items": items,
        "sample_note": "当前筛选结果仅包含一位艺人，暂不具备横向比较意义" if len(items) == 1 else "",
        "note": _empty_note(items, "艺人对比"),
    }


# Explicit aliases make the service API easy to discover and keep route names
# independent from the data-shape names above.
aggregate_map = map_data
aggregate_trends = trend_data
aggregate_calendar = calendar_data
aggregate_prices = price_data
aggregate_topics = topic_data
aggregate_artists = artist_data


def sources_data(concerts):
    """按数据来源统计场次，回应「哪部分是爬取的、哪部分是公开数据集」的复查需求。"""
    by_source = defaultdict(lambda: {"concerts": 0, "artists": set(), "cities": set()})
    total = 0
    for concert in concerts:
        source = _value(concert, "source_type") or "未标注"
        by_source[source]["concerts"] += 1
        artist = _value(concert, "artist_name")
        city = _value(concert, "city")
        if artist:
            by_source[source]["artists"].add(artist)
        if city:
            by_source[source]["cities"].add(city)
        total += 1
    items = [
        {
            "source": source,
            "concerts": value["concerts"],
            "artists": len(value["artists"]),
            "cities": len(value["cities"]),
        }
        for source, value in sorted(by_source.items(), key=lambda pair: -pair[1]["concerts"])
    ]
    return {"items": items, "total": total, "note": _empty_note(items, "来源统计")}


aggregate_sources = sources_data
