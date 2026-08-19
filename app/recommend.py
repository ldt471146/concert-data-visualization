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
    city = filters.get("city")
    status = filters.get("status")
    artist = filters.get("artist")
    start = filters.get("start")
    end = filters.get("end")
    min_price = filters.get("min_price")
    max_price = filters.get("max_price")

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
    for concert in query.order_by(ConcertInfo.show_time.asc()).all():
        if not price_matches(concert, min_price, max_price):
            continue
        comments = concert.comments
        likes = sum(comment.like_count or 0 for comment in comments)
        comment_count = len(comments)
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
