import csv
from datetime import datetime
from pathlib import Path


from .analysis import run_analysis
from .extensions import db
from .models import CommentInfo, ConcertInfo, JobRun, TicketPriceDetail
from .time_utils import utcnow
from .validation import (
    SALE_STATUSES,
    concert_fingerprint,
    parse_csv_rows,
    parse_datetime_strict,
    parse_price_values,
    validate_csv,
    value,
)


def parse_datetime(value_text):
    """Keep the seed-data fallback while imports use strict validation."""
    return parse_datetime_strict(value_text) or utcnow()


def parse_prices(text):
    numbers = parse_price_values(text)
    if not numbers:
        return None, None
    return min(numbers), max(numbers)


def _value(row, *keys):
    return value(row, *keys)


def _row_error(row_number, field, code, message):
    return {"row": row_number, "field": field, "code": code, "message": message}


def _existing_concert_fingerprints():
    return {
        concert_fingerprint(
            {
                "concert_name": concert.concert_name,
                "city": concert.city,
                "show_time": concert.show_time,
                "venue": concert.venue,
            }
        )
        for concert in ConcertInfo.query.all()
    }


def import_csv(stream, kind, filename=""):
    """Import valid rows and return a non-sensitive, structured quality report."""
    if hasattr(stream, "read"):
        content = stream.read()
    else:
        content = stream

    report = validate_csv(content, kind, filename)
    try:
        rows, _ = parse_csv_rows(content)
    except (UnicodeDecodeError, csv.Error, TypeError, ValueError):
        report.update({"input_count": 0, "success_count": 0, "failed_count": 0})
        return report

    success = 0
    failed = 0
    duplicate_count = report.get("duplicate_count", 0)
    errors = list(report.get("errors", []))
    hard_error_rows = {
        error["row"]
        for error in errors
        if error.get("row", 0) > 1 and error.get("code") != "duplicate"
    }
    duplicate_rows = {
        error["row"] for error in errors if error.get("code") == "duplicate"
    }

    if kind == "concerts":
        existing = _existing_concert_fingerprints()
        for row_number, row in enumerate(rows, start=2):
            fingerprint = concert_fingerprint(row)
            if row_number in duplicate_rows or fingerprint in existing:
                if fingerprint not in existing:
                    duplicate_count += 1
                elif row_number not in duplicate_rows:
                    duplicate_count += 1
                    errors.append(_row_error(row_number, "concert_name", "duplicate", "演唱会指纹已存在"))
                continue
            if row_number in hard_error_rows:
                failed += 1
                continue
            try:
                show_time = parse_datetime_strict(_value(row, "show_time"))
                min_price, max_price = parse_prices(_value(row, "price_text"))
                concert = ConcertInfo(
                    artist_name=_value(row, "artist_name") or "周杰伦",
                    concert_name=_value(row, "concert_name"),
                    city=_value(row, "city"),
                    venue=_value(row, "venue"),
                    show_time=show_time,
                    price_text=_value(row, "price_text"),
                    min_price=min_price,
                    max_price=max_price,
                    sale_status=_value(row, "sale_status") or "待定",
                    source_url=_value(row, "source_url") or "local://data/raw/concerts.csv",
                    collected_at=parse_datetime(_value(row, "collected_at")),
                )
                db.session.add(concert)
                db.session.flush()
                if min_price is not None:
                    db.session.add(
                        TicketPriceDetail(
                            price_label="标准票档",
                            price=min_price,
                            price_text=concert.price_text,
                            concert_id=concert.id,
                        )
                    )
                existing.add(fingerprint)
                success += 1
            except Exception:
                db.session.rollback()
                failed += 1
                errors.append(_row_error(row_number, "row", "save_error", "记录无法保存"))
        db.session.commit()
    elif kind == "comments":
        concert_map = {concert.concert_name: concert.id for concert in ConcertInfo.query.all()}
        existing_text = {comment.comment_text for comment in CommentInfo.query.all()}
        for row_number, row in enumerate(rows, start=2):
            text = _value(row, "comment_text")
            if text in existing_text:
                failed += 1
                errors.append(_row_error(row_number, "comment_text", "duplicate", "评论内容已存在"))
                continue
            if row_number in hard_error_rows:
                failed += 1
                continue
            try:
                comment = CommentInfo(
                    concert_id=concert_map.get(_value(row, "concert_name")),
                    comment_text=text,
                    comment_time=parse_datetime(_value(row, "comment_time")),
                    like_count=int(float(_value(row, "like_count") or 0)),
                    user_region=_value(row, "user_region") or "未提供",
                    source_url=_value(row, "source_url") or "local://data/raw/comments.csv",
                    collected_at=parse_datetime(_value(row, "collected_at")),
                )
                db.session.add(comment)
                existing_text.add(text)
                success += 1
            except Exception:
                db.session.rollback()
                failed += 1
                errors.append(_row_error(row_number, "row", "save_error", "记录无法保存"))
        db.session.commit()
    else:
        return report

    report.update(
        {
            "input_count": len(rows),
            "success_count": success,
            "failed_count": failed,
            "duplicate_count": duplicate_count,
            "errors": errors,
            "error_count": len(errors),
        }
    )
    return report



def seed_demo_data():
    if ConcertInfo.query.count() > 0:
        return {"seeded": False, "concerts": ConcertInfo.query.count(), "comments": CommentInfo.query.count()}

    concerts = [
        ("周杰伦", "嘉年华 · 上海场", "上海", "梅赛德斯-奔驰文化中心", "2025-05-18 19:30", "580 / 880 / 1280 / 1680", "已售罄"),
        ("周杰伦", "嘉年华 · 北京场", "北京", "国家体育场", "2025-06-01 19:30", "680 / 980 / 1380 / 1880", "售票中"),
        ("周杰伦", "嘉年华 · 深圳场", "深圳", "深圳湾体育中心", "2025-06-15 19:30", "580 / 880 / 1180 / 1680", "售票中"),
        ("周杰伦", "嘉年华 · 成都场", "成都", "东安湖体育公园", "2025-06-29 19:30", "480 / 780 / 1080 / 1580", "即将开售"),
        ("周杰伦", "嘉年华 · 杭州场", "杭州", "黄龙体育中心", "2025-07-06 19:30", "580 / 880 / 1280 / 1780", "售票中"),
        ("周杰伦", "嘉年华 · 广州场", "广州", "宝能广州国际体育演艺中心", "2025-07-20 19:30", "680 / 980 / 1380 / 1880", "待定"),
        ("周杰伦", "嘉年华 · 南京场", "南京", "南京奥体中心", "2025-08-03 19:30", "480 / 780 / 1080 / 1580", "售票中"),
        ("周杰伦", "嘉年华 · 重庆场", "重庆", "华熙LIVE·鱼洞", "2025-08-17 19:30", "580 / 880 / 1180 / 1680", "即将开售"),
        ("周杰伦", "嘉年华 · 武汉场", "武汉", "武汉五环体育中心", "2025-09-07 19:30", "480 / 780 / 1080 / 1580", "售票中"),
        ("周杰伦", "嘉年华 · 西安场", "西安", "西安奥体中心", "2025-09-21 19:30", "580 / 880 / 1280 / 1780", "待定"),
        ("周杰伦", "嘉年华 · 厦门场", "厦门", "厦门体育中心", "2025-10-05 19:30", "680 / 980 / 1380 / 1880", "售票中"),
        ("周杰伦", "嘉年华 · 青岛场", "青岛", "青岛青春足球场", "2025-10-19 19:30", "580 / 880 / 1180 / 1680", "即将开售"),
    ]
    created = []
    for artist, name, city, venue, date_text, price_text, status in concerts:
        min_price, max_price = parse_prices(price_text)
        concert = ConcertInfo(
            artist_name=artist,
            concert_name=name,
            city=city,
            venue=venue,
            show_time=parse_datetime(date_text),
            price_text=price_text,
            min_price=min_price,
            max_price=max_price,
            sale_status=status,
            source_url="local://data/raw/concerts.csv",
            collected_at=parse_datetime("2025-04-18 10:00:00"),
        )
        db.session.add(concert)
        created.append(concert)
    db.session.flush()
    for concert in created:
        min_price, _ = parse_prices(concert.price_text)
        db.session.add(TicketPriceDetail(price_label="最低票档", price=min_price, price_text=concert.price_text, concert_id=concert.id))

    comments = [
        (0, "现场灯光和编曲比视频里更有层次，开场就被震撼到了。", 328, "上海"),
        (0, "终于等到现场，整晚的情绪一直被带着走。", 214, "江苏"),
        (0, "场馆动线有点拥挤，但歌单和舞台真的值得。", 86, "浙江"),
        (1, "北京场的期待值拉满，希望能听到那首歌。", 192, "北京"),
        (1, "票价区间看得很清楚，已经选好位置了。", 74, "河北"),
        (1, "购票流程顺利，期待夏天见。", 135, "北京"),
        (2, "副歌响起来的时候全场合唱，太感动了。", 411, "广东"),
        (2, "舞台屏幕很清晰，视线体验比预期好。", 153, "湖南"),
        (2, "价格和视野需要多比较一下，其他都很期待。", 45, "广东"),
        (3, "成都的氛围一直很热烈，现场应该会很精彩。", 184, "四川"),
        (3, "希望开售时间能早点公布。", 66, "重庆"),
        (3, "本地交通方便，已经约好朋友一起去。", 118, "四川"),
        (4, "杭州场的舞美期待值很高。", 163, "浙江"),
        (4, "听到熟悉的前奏那一刻特别感动。", 289, "安徽"),
        (4, "价格有一点高，但还是值得体验一次。", 92, "浙江"),
        (5, "场馆很大，希望远区也能看清屏幕。", 81, "广东"),
        (5, "歌单如果再长一点就更好了。", 38, "广西"),
        (5, "每一首歌都很有记忆点，太喜欢了。", 241, "广东"),
        (6, "南京场的日期很合适，准备冲现场。", 121, "江苏"),
        (6, "从学生时代听到现在，现场一定会哭。", 307, "安徽"),
        (6, "希望不要遇到临时延迟。", 32, "江苏"),
        (7, "重庆的现场气氛应该很炸，已经开始期待。", 219, "重庆"),
        (7, "看过之前的舞台，灯光设计真的很精彩。", 170, "四川"),
        (7, "排队时间有点担心，想提前规划路线。", 58, "重庆"),
        (8, "武汉场的票档很友好，准备和家人一起去。", 144, "湖北"),
        (8, "现场的情绪感染力太强了，每次都会被感动。", 261, "湖北"),
        (8, "希望场馆周边的交通安排更顺畅。", 49, "江西"),
        (9, "西安场很期待，城市和音乐放在一起很有感觉。", 177, "陕西"),
        (9, "已经收藏了这场，等售票状态更新。", 96, "陕西"),
        (10, "厦门的海风和现场音乐，想想就很开心。", 231, "福建"),
        (10, "如果能增加返场就完美了。", 73, "福建"),
        (10, "价格透明，信息整理得很方便。", 127, "广东"),
        (11, "青岛场的日期很适合旅行，期待值很高。", 189, "山东"),
        (11, "希望能顺利买到票，现场见。", 148, "山东"),
        (11, "场地离市区有点远，需要提前安排。", 54, "山东"),
    ]
    for concert_index, text, likes, region in comments:
        db.session.add(
            CommentInfo(
                concert_id=created[concert_index].id,
                comment_text=text,
                comment_time=datetime(2025, 3 + (concert_index % 4), 5 + concert_index, 12, 0),
                like_count=likes,
                user_region=region,
                source_url="local://data/raw/comments.csv",
                collected_at=parse_datetime("2025-04-18 10:00:00"),
            )
        )
    db.session.commit()
    run_analysis()
    return {"seeded": True, "concerts": len(created), "comments": len(comments)}


def load_local_concert_snapshot(snapshot_path):
    """Load the checked local concert snapshot once the seed data exists."""
    path = Path(snapshot_path)
    if not path.exists():
        return {"input_count": 0, "success_count": 0, "failed_count": 0, "missing": True}
    with path.open("rb") as stream:
        result = import_csv(stream, "concerts", path.name)
    if result.get("success_count", 0):
        run_analysis()
    return result


def create_job(job_type):
    job = JobRun(job_type=job_type, status="running")
    db.session.add(job)
    db.session.commit()
    return job


def finish_job(job, status, result=None, message=""):
    result = result or {}
    job.status = status
    job.input_count = result.get("input_count", result.get("comments", result.get("concerts", 0)))
    job.success_count = result.get("success_count", result.get("comments", result.get("concerts", 0)))
    job.failed_count = result.get("failed_count", 0)
    job.message = message or ("分析完成" if job.job_type == "analysis" else "导入完成")
    job.finished_at = utcnow()
    db.session.commit()
    return job
