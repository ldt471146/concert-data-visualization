import csv
import io

from flask import Blueprint, Response, jsonify, render_template, request
from flask_login import current_user, login_required

from .analysis import run_analysis
from .extensions import db
from .models import ConcertInfo, JobRun
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

