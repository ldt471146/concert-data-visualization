from .models import ConcertInfo


def price_matches(concert, low=None, high=None):
    concert_min = float(concert.min_price) if concert.min_price is not None else None
    concert_max = float(concert.max_price) if concert.max_price is not None else concert_min
    if low is not None and (concert_max is None or concert_max < low):
        return False
    if high is not None and (concert_min is None or concert_min > high):
        return False
    return True


def build_recommendations(filters=None, limit=4):
    filters = filters or {}
    query = ConcertInfo.query
    category = filters.get("category")
    city = filters.get("city")
    status = filters.get("status")
    artist = filters.get("artist")
    start = filters.get("start")
    end = filters.get("end")
    min_price = filters.get("min_price")
    max_price = filters.get("max_price")

    if category and category != "全部":
        query = query.filter(ConcertInfo.category == category)
    if city and city != "全部":
        query = query.filter(ConcertInfo.city == city)
    if status and status != "全部":
        query = query.filter(ConcertInfo.sale_status == status)
    if artist and artist != "全部":
        query = query.filter(ConcertInfo.artist_name == artist)
    if start:
        query = query.filter(ConcertInfo.show_time >= start)
    if end:
        query = query.filter(ConcertInfo.show_time <= end)

    recommendations = []
    # 用 SQL 聚合统计评论数/点赞数, 避免全量加载 19 万评论对象到内存
    from sqlalchemy import func
    from .models import CommentInfo as _CI
    agg_rows = {
        row[0]: (row[1], row[2])
        for row in query.join(_CI, _CI.concert_id == ConcertInfo.id, isouter=True)
        .with_entities(
            ConcertInfo.id,
            func.count(_CI.id),
            func.coalesce(func.sum(_CI.like_count), 0),
        )
        .group_by(ConcertInfo.id)
        .all()
    }
    concerts_batch = query.order_by(ConcertInfo.show_time.asc()).all()
    for concert in concerts_batch:
        if not price_matches(concert, min_price, max_price):
            continue
        comment_count, likes = agg_rows.get(concert.id, (0, 0))
        score = 54.0
        score += min(comment_count * 2.8, 19)
        score += min(likes / 120, 12)
        score += 8 if concert.sale_status == "售票中" else 4 if concert.sale_status == "即将开售" else 2
        if concert.min_price and float(concert.min_price) <= 880:
            score += 5
        score = round(min(score, 98), 1)
        reasons = []
        if comment_count >= 3:
            reasons.append("讨论度高")
        if concert.sale_status == "售票中":
            reasons.append("当前可购")
        if concert.min_price and float(concert.min_price) <= 880:
            reasons.append("入场门槛友好")
        recommendations.append(
            {
                **concert.to_dict(),
                "score": score,
                "reason": " · ".join(reasons[:2]) or "符合当前筛选",
                "likes": likes,
            }
        )

    recommendations.sort(key=lambda item: (-item["score"], item["show_time"]))
    return recommendations[:limit]
