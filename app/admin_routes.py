import csv
import io

from flask import Blueprint, Response, jsonify, render_template, request
from flask_login import current_user, login_required

from .analysis import run_analysis
from .cache import clear_cache
from .extensions import db
from sqlalchemy import func

from .models import AnalysisResult, CommentInfo, ConcertInfo, JobRun
from .services import create_job, finish_job, import_csv, parse_prices, seed_demo_data
from .validation import SALE_STATUSES, parse_datetime_strict, validate_csv


admin = Blueprint("admin", __name__, url_prefix="/admin")

_SAFE_IMPORT_FAILURE = "导入失败，请检查 CSV 字段。"


@admin.get("")
@login_required
def dashboard():
    jobs = JobRun.query.order_by(JobRun.started_at.desc()).limit(12).all()
    return render_template("admin.html", jobs=[job.to_dict() for job in jobs], admin_name=current_user.username)


@admin.get("/api/jobs")
@login_required
def jobs():
    return jsonify({"items": [job.to_dict() for job in JobRun.query.order_by(JobRun.started_at.desc()).limit(20).all()]})


@admin.get("/api/jobs/<int:job_id>")
@login_required
def job_detail(job_id):
    job = db.session.get(JobRun, job_id)
    if not job:
        return jsonify({"error": "任务不存在。"}), 404
    return jsonify({"job": job.to_dict()})


@admin.post("/api/import/preview")
@login_required
def import_preview():
    uploaded = request.files.get("file")
    kind = request.form.get("kind", "concerts")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "请选择 CSV 文件。"}), 400
    if kind not in {"concerts", "comments"}:
        return jsonify({"error": "不支持的数据类型。"}), 400
    try:
        report = validate_csv(uploaded.stream.read(), kind, uploaded.filename)
    except Exception:
        report = {
            "filename": uploaded.filename,
            "kind": kind,
            "fields": [],
            "total_rows": 0,
            "preview": [],
            "errors": [{"row": 0, "field": "file", "code": "invalid_csv", "message": "CSV 文件无法解析"}],
            "valid": False,
        }
    payload = {"ok": True, "report": report}
    payload.update(report)
    return jsonify(payload)


@admin.post("/api/import")
@login_required
def import_data():
    uploaded = request.files.get("file")
    kind = request.form.get("kind", "concerts")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "请选择 CSV 文件。"}), 400
    if kind not in {"concerts", "comments"}:
        return jsonify({"error": "不支持的数据类型。"}), 400

    job = create_job(f"import_{kind}")
    try:
        result = import_csv(uploaded.stream, kind, uploaded.filename)
        clear_cache()
        finish_job(job, "success", result, "CSV 导入完成")
        return jsonify({"ok": True, "result": result, "report": result, "job": job.to_dict()})
    except Exception:
        db.session.rollback()
        finish_job(
            job,
            "failed",
            {"input_count": 0, "success_count": 0, "failed_count": 1},
            _SAFE_IMPORT_FAILURE,
        )
        return jsonify({"error": _SAFE_IMPORT_FAILURE}), 400


@admin.get("/api/export/concerts")
@login_required
def export_concerts():
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "artist_name",
            "concert_name",
            "city",
            "venue",
            "show_time",
            "price_text",
            "min_price",
            "max_price",
            "sale_status",
            "source_url",
            "collected_at",
        ]
    )
    for concert in ConcertInfo.query.order_by(ConcertInfo.show_time.asc()).all():
        writer.writerow(
            [
                concert.id,
                concert.artist_name,
                concert.concert_name,
                concert.city,
                concert.venue,
                concert.show_time.isoformat(),
                concert.price_text,
                concert.min_price if concert.min_price is not None else "",
                concert.max_price if concert.max_price is not None else "",
                concert.sale_status,
                concert.source_url,
                concert.collected_at.isoformat() if concert.collected_at else "",
            ]
        )
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=concerts.csv"
    return response


@admin.route("/api/concerts/<int:concert_id>", methods=["PUT", "PATCH"])
@login_required
def update_concert(concert_id):
    concert = db.session.get(ConcertInfo, concert_id)
    if not concert:
        return jsonify({"error": "演唱会记录不存在。"}), 404
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict()
    if not isinstance(payload, dict) or not payload:
        return jsonify({"error": "请提供要修改的字段。"}), 400

    allowed = {"name", "concert_name", "venue", "time", "show_time", "price_text", "sale_status"}
    unknown = set(payload) - allowed
    if unknown:
        return jsonify({"error": "仅允许修改名称、场馆、时间、价格文本和售票状态。"}), 400
    if "name" in payload and "concert_name" in payload:
        return jsonify({"error": "名称字段只能提供一个。"}), 400

    if "name" in payload or "concert_name" in payload:
        name = str(payload.get("name", payload.get("concert_name", ""))).strip()
        if not name:
            return jsonify({"error": "演唱会名称不能为空。"}), 400
        concert.concert_name = name
    if "venue" in payload:
        venue = str(payload["venue"]).strip()
        if not venue:
            return jsonify({"error": "场馆不能为空。"}), 400
        concert.venue = venue
    if "time" in payload or "show_time" in payload:
        raw_time = payload.get("time", payload.get("show_time"))
        show_time = parse_datetime_strict(raw_time)
        if show_time is None:
            return jsonify({"error": "演出时间格式无法解析。"}), 400
        concert.show_time = show_time
    if "price_text" in payload:
        concert.price_text = str(payload["price_text"]).strip()
        concert.min_price, concert.max_price = parse_prices(concert.price_text)
    if "sale_status" in payload:
        sale_status = str(payload["sale_status"]).strip()
        if sale_status not in SALE_STATUSES:
            return jsonify({"error": "售票状态不在允许范围内。"}), 400
        concert.sale_status = sale_status

    try:
        db.session.commit()
        clear_cache()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "演唱会记录更新失败。"}), 500
    return jsonify({"ok": True, "concert": concert.to_dict()})


@admin.delete("/api/concerts/<int:concert_id>")
@login_required
def delete_concert(concert_id):
    concert = db.session.get(ConcertInfo, concert_id)
    if not concert:
        return jsonify({"error": "演唱会记录不存在。"}), 404
    try:
        db.session.delete(concert)
        db.session.commit()
        clear_cache()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "演唱会记录删除失败。"}), 500
    return jsonify({"ok": True, "deleted_id": concert_id})


@admin.post("/api/analyze")
@login_required
def analyze():
    job = create_job("analysis")
    try:
        result = run_analysis()
        clear_cache()
        finish_job(job, "success", result, "评论分析与统计已更新")
        return jsonify({"ok": True, "result": result, "job": job.to_dict()})
    except Exception:
        db.session.rollback()
        finish_job(job, "failed", {"input_count": 0, "success_count": 0, "failed_count": 1}, "分析失败，请检查数据。")
        return jsonify({"error": "分析失败，请检查数据。"}), 500


@admin.post("/api/seed")
@login_required
def seed():
    try:
        result = seed_demo_data()
        return jsonify({"ok": True, "result": result})
    except Exception:
        db.session.rollback()
        return jsonify({"error": "示例数据初始化失败。"}), 500



# ---------------------------------------------------------------------------
# 管理后台增强接口：仪表盘统计 / 数据管理 / 运维
# ---------------------------------------------------------------------------


@admin.get("/api/stats")
@login_required
def stats():
    """后台仪表盘统计：总量、来源分布、近 7 日场次趋势、最近评论样本。"""
    concert_total = ConcertInfo.query.count()
    comment_total = CommentInfo.query.count()
    artist_total = ConcertInfo.query.with_entities(ConcertInfo.artist_name).distinct().count()
    city_total = ConcertInfo.query.with_entities(ConcertInfo.city).distinct().count()

    by_source_rows = (
        ConcertInfo.query.with_entities(ConcertInfo.source_type, func.count(ConcertInfo.id))
        .group_by(ConcertInfo.source_type).all()
    )
    sources = [
        {"source": source or "未标注", "count": count}
        for source, count in sorted(by_source_rows, key=lambda row: -row[1])
    ]

    job_total = JobRun.query.count()
    failed_jobs = JobRun.query.filter(JobRun.status == "failed").count()

    recent_days_rows = (
        ConcertInfo.query.with_entities(
            func.strftime("%Y-%m-%d", ConcertInfo.show_time),
            func.count(ConcertInfo.id),
        )
        .group_by(func.strftime("%Y-%m-%d", ConcertInfo.show_time))
        .order_by(func.strftime("%Y-%m-%d", ConcertInfo.show_time).desc())
        .limit(7).all()
    )
    days = [{"date": day, "count": count} for day, count in reversed(recent_days_rows)]

    recent_comments = (
        CommentInfo.query.order_by(CommentInfo.comment_time.desc().nullslast())
        .limit(5).all()
    )

    return jsonify({
        "totals": {
            "concerts": concert_total,
            "comments": comment_total,
            "artists": artist_total,
            "cities": city_total,
        },
        "sources": sources,
        "jobs": {"total": job_total, "failed": failed_jobs},
        "recent_days": days,
        "recent_comments": [comment.to_dict() for comment in recent_comments],
    })


@admin.get("/api/concerts")
@login_required
def list_concerts():
    """演唱会分页管理：支持关键字、艺人、城市、状态筛选。"""
    q = request.args.get("q", "").strip()
    artist = request.args.get("artist", "").strip()
    city = request.args.get("city", "").strip()
    status = request.args.get("status", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1) or 1))
        size = min(100, max(5, int(request.args.get("size", 20) or 20)))
    except ValueError:
        page, size = 1, 20

    query = ConcertInfo.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                ConcertInfo.artist_name.like(like),
                ConcertInfo.concert_name.like(like),
                ConcertInfo.venue.like(like),
            )
        )
    if artist:
        query = query.filter(ConcertInfo.artist_name == artist)
    if city:
        query = query.filter(ConcertInfo.city == city)
    if status:
        query = query.filter(ConcertInfo.sale_status == status)

    total = query.count()
    items = (
        query.order_by(ConcertInfo.show_time.desc())
        .offset((page - 1) * size).limit(size).all()
    )
    return jsonify({
        "items": [concert.to_dict() for concert in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, (total + size - 1) // size),
    })


@admin.get("/api/concerts/summary")
@login_required
def concert_summary():
    """管理后台筛选器选项：全部艺人、城市、售票状态（去重排序）。"""
    artists = [row[0] for row in db.session.query(ConcertInfo.artist_name).distinct().order_by(ConcertInfo.artist_name).all()]
    cities = [row[0] for row in db.session.query(ConcertInfo.city).distinct().order_by(ConcertInfo.city).all()]
    statuses = [row[0] for row in db.session.query(ConcertInfo.sale_status).distinct().order_by(ConcertInfo.sale_status).all()]
    return jsonify({"artists": artists, "cities": cities, "statuses": statuses})


@admin.get("/api/comments")
@login_required
def list_comments():
    """评论分页管理：支持评论内容、艺人名关键字筛选。"""
    q = request.args.get("q", "").strip()
    artist = request.args.get("artist", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1) or 1))
        size = min(100, max(5, int(request.args.get("size", 20) or 20)))
    except ValueError:
        page, size = 1, 20

    query = CommentInfo.query
    if q:
        query = query.filter(CommentInfo.comment_text.like(f"%{q}%"))
    if artist:
        by_artist_ids = (
            ConcertInfo.query.with_entities(ConcertInfo.id)
            .filter(ConcertInfo.artist_name == artist).all()
        )
        ids = [row[0] for row in by_artist_ids]
        if not ids:
            return jsonify({"items": [], "total": 0, "page": page, "size": size, "pages": 1})
        query = query.filter(CommentInfo.concert_id.in_(ids))

    total = query.count()
    items = (
        query.order_by(CommentInfo.comment_time.desc().nullslast())
        .offset((page - 1) * size).limit(size).all()
    )
    return jsonify({
        "items": [comment.to_dict() for comment in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, (total + size - 1) // size),
    })


@admin.delete("/api/comments/<int:comment_id>")
@login_required
def delete_comment(comment_id):
    comment = db.session.get(CommentInfo, comment_id)
    if not comment:
        return jsonify({"error": "评论不存在。"}), 404
    try:
        db.session.delete(comment)
        db.session.commit()
        clear_cache()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "评论删除失败。"}), 500
    return jsonify({"ok": True, "deleted_id": comment_id})


@admin.post("/api/concerts/batch-delete")
@login_required
def batch_delete_concerts():
    """批量删除演唱会：同步删除关联评论。"""
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids") or []
    ids = [int(item) for item in ids if str(item).isdigit()]
    if not ids:
        return jsonify({"error": "未选择要删除的记录。"}), 400
    try:
        CommentInfo.query.filter(CommentInfo.concert_id.in_(ids)).delete(synchronize_session=False)
        deleted = ConcertInfo.query.filter(ConcertInfo.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        clear_cache()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "批量删除失败。"}), 500
    return jsonify({"ok": True, "deleted": deleted})


@admin.get("/api/export/comments")
@login_required
def export_comments():
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        ["id", "concert_id", "comment_text", "comment_time", "like_count", "user_region", "sentiment_score", "source_url"]
    )
    for comment in CommentInfo.query.order_by(CommentInfo.comment_time.asc()).all():
        writer.writerow(
            [
                comment.id,
                comment.concert_id if comment.concert_id is not None else "",
                comment.comment_text,
                comment.comment_time.isoformat() if comment.comment_time else "",
                comment.like_count if comment.like_count is not None else "",
                comment.user_region or "",
                comment.sentiment_score if comment.sentiment_score is not None else "",
                comment.source_url,
            ]
        )
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=comments.csv"
    return response


@admin.post("/api/cache/clear")
@login_required
def cache_clear():
    """清空 Redis 分析缓存，常用在数据变更后强制刷新看板。"""
    cleared = clear_cache()
    return jsonify({"ok": True, "cleared": cleared})
