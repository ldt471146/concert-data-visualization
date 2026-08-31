import csv
import io
from collections import Counter
from pathlib import Path

import pytest
from app import create_app
from app.extensions import db
from app.models import ConcertInfo, CommentInfo


@pytest.fixture()
def client(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "ADMIN_USERNAME": "atlas",
        "ADMIN_PASSWORD": "pulse2025",
    })
    with app.test_client() as test_client:
        yield test_client
    with app.app_context():
        db.drop_all()


def login(client):
    return client.post("/login", data={"username": "atlas", "password": "pulse2025"}, follow_redirects=False)


def test_public_health_and_overview(client):
    health = client.get("/api/health")
    overview = client.get("/api/overview")
    assert health.status_code == 200
    assert health.json["status"] == "ok"
    assert health.json["concerts"] == 12
    assert overview.status_code == 200
    assert overview.json["metrics"]["comments"] == 35
    assert overview.json["charts"]["city"]
    assert overview.json["recommendations"]


def test_filter_changes_payload(client):
    response = client.get("/api/overview?city=北京")
    assert response.status_code == 200
    assert response.json["metrics"]["concerts"] == 1
    assert response.json["concerts"][0]["city"] == "北京"


def test_price_filter_and_invalid_number_are_safe(client):
    filtered = client.get("/api/overview?min_price=1700")
    assert filtered.status_code == 200
    assert filtered.json["metrics"]["concerts"] < 12
    invalid = client.get("/api/overview?min_price=not-a-number")
    assert invalid.status_code == 200
    assert invalid.json["metrics"]["concerts"] == 12


def test_admin_requires_login_and_accepts_credentials(client):
    assert client.get("/admin").status_code == 302
    response = login(client)
    assert response.status_code == 302
    assert client.get("/admin").status_code == 200


def test_admin_analysis_and_import(client):
    login(client)
    analysis = client.post("/admin/api/analyze")
    assert analysis.status_code == 200
    assert analysis.json["job"]["status"] == "success"

    csv_data = "artist_name,concert_name,city,venue,show_time,price_text,sale_status\n周杰伦,测试场,苏州,苏州体育中心,2025-11-01 19:30,580 / 880,售票中\n"
    imported = client.post(
        "/admin/api/import",
        data={"kind": "concerts", "file": (io.BytesIO(csv_data.encode("utf-8")), "concerts.csv")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 200
    assert imported.json["job"]["success_count"] == 1
    jobs = client.get("/admin/api/jobs")
    assert jobs.status_code == 200
    assert any(job["job_type"] == "import_concerts" for job in jobs.json["items"])


def test_logout(client):
    login(client)
    assert client.get("/logout").status_code == 302
    assert client.get("/admin").status_code == 302


def test_extended_analytics_endpoints(client):
    endpoints = ("map", "trend", "calendar", "prices", "topics", "artists")
    for name in endpoints:
        response = client.get(f"/api/analytics/{name}")
        assert response.status_code == 200
        assert isinstance(response.json, dict)
    assert client.get("/api/analytics/map?city=不存在").json["items"] == []
    invalid = client.get("/api/analytics/trend?start=bad-date&min_price=bad-number")
    assert invalid.status_code == 200
    assert "无效" in invalid.json.get("note", "")


def test_admin_preview_detail_export_and_edit(client):
    login(client)
    csv_data = "artist_name,concert_name,city,venue,show_time,price_text,sale_status\n周杰伦,预览场,苏州,苏州体育中心,2025-11-01 19:30,580 / 880,售票中\n周杰伦,预览场,苏州,苏州体育中心,2025-11-01 19:30,580 / 880,售票中\n"
    preview = client.post(
        "/admin/api/import/preview",
        data={"kind": "concerts", "file": (io.BytesIO(csv_data.encode("utf-8")), "preview.csv")},
        content_type="multipart/form-data",
    )
    assert preview.status_code == 200
    assert preview.json["report"]["duplicate_count"] == 1
    assert preview.json["report"]["preview"]

    export = client.get("/admin/api/export/concerts")
    assert export.status_code == 200
    assert "concert_name" in export.get_data(as_text=True)

    detail = client.get("/admin/api/jobs/99999")
    assert detail.status_code == 404
    update = client.put("/admin/api/concerts/1", json={"venue": "测试场馆", "price_text": "300 / 900"})
    assert update.status_code == 200
    assert update.json["concert"]["venue"] == "测试场馆"
    assert update.json["concert"]["min_price"] == 300


def test_public_snapshot_contains_multiple_artists_and_cities():
    path = Path(__file__).resolve().parents[1] / "data" / "raw" / "concerts.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 78
    assert len(Counter(row["artist_name"] for row in rows)) == 57
    assert len(Counter(row["city"] for row in rows)) == 12
    assert all(row["source_url"] and row["collected_at"] for row in rows)


def test_fresh_app_loads_local_snapshot(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'fresh.db'}",
        "LOAD_LOCAL_SNAPSHOT": True,
    })
    with app.app_context():
        count = ConcertInfo.query.count()
        # 有合并快照时加载 merged（十万级），否则回退 78 条基础快照
        merged = Path(__file__).resolve().parents[1] / "data" / "raw" / "concerts_merged.csv"
        assert count == 78 or (merged.exists() and count > 78)
        db.drop_all()


def test_bulk_data_sources_files_exist():
    root = Path(__file__).resolve().parents[1]
    nyphil = root / "data" / "raw" / "nyphil_concerts.csv"
    showstart = root / "data" / "raw" / "showstart_concerts.csv"
    mb = root / "data" / "raw" / "musicbrainz_events.csv"
    with nyphil.open(encoding="utf-8-sig", newline="") as handle:
        nyphil_rows = list(csv.DictReader(handle))
    with showstart.open(encoding="utf-8-sig", newline="") as handle:
        showstart_rows = list(csv.DictReader(handle))
    assert len(nyphil_rows) > 20000
    assert len(showstart_rows) > 100
    assert all(row["source_type"] in ("公开数据集", "爬虫采集") for row in nyphil_rows + showstart_rows)
    assert all(row["source_url"] and row["collected_at"] for row in nyphil_rows + showstart_rows)
    if mb.exists():
        with mb.open(encoding="utf-8-sig", newline="") as handle:
            mb_rows = list(csv.DictReader(handle))
        assert mb_rows, "musicbrainz_events.csv 不应为空"


def test_bulk_100k_data_files_reach_target():
    root = Path(__file__).resolve().parents[1]
    comments = root / "data" / "raw" / "comments_wyy_merged.csv"
    concerts = root / "data" / "raw" / "concerts_merged.csv"
    with comments.open(encoding="utf-8-sig", newline="") as handle:
        comment_rows = list(csv.DictReader(handle))
    with concerts.open(encoding="utf-8-sig", newline="") as handle:
        concert_rows = list(csv.DictReader(handle))
    # 演唱会记录 + 评论记录 合计 >= 10 万条
    assert len(comment_rows) + len(concert_rows) >= 100000
    # 艺人量级: 演唱会去重艺人超过 100 位
    assert len(Counter(r["artist_name"] for r in concert_rows if r["artist_name"])) >= 100
    # 来源标注: 记录都带 source_type 与来源地址
    for r in concert_rows[:200]:
        assert r["source_type"] and r["source_url"]



def test_admin_concert_and_comment_pagination(client):
    login(client)
    concerts = client.get("/admin/api/concerts?page=1&size=5")
    assert concerts.status_code == 200
    assert concerts.json["items"]
    assert concerts.json["total"] > 0
    assert concerts.json["pages"] >= 1
    comments = client.get("/admin/api/comments?page=1&size=5")
    assert comments.status_code == 200
    assert comments.json["total"] > 0


def test_admin_stats_and_summary(client):
    login(client)
    stats = client.get("/admin/api/stats")
    assert stats.status_code == 200
    assert stats.json["totals"]["concerts"] > 0
    assert stats.json["totals"]["comments"] > 0
    summary = client.get("/admin/api/concerts/summary")
    assert summary.status_code == 200
    assert summary.json["artists"]
    assert summary.json["cities"]


def test_admin_export_comments(client):
    login(client)
    response = client.get("/admin/api/export/comments")
    assert response.status_code == 200
    assert response.data[:6] == b"id,con"


def test_concert_detail_and_pagination(client):
    """场次详情接口: 基本信息 + 票价 + 评论分页。"""
    detail = client.get("/api/concerts/1")
    assert detail.status_code == 200
    body = detail.json
    assert body["concert"]["id"] == 1
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["pages"] >= 1
    assert body["pagination"]["total"] >= 0
    # 翻页
    page2 = client.get("/api/concerts/1?page=9999")
    assert page2.status_code == 200
    # 不存在返回 404
    missing = client.get("/api/concerts/9999999")
    assert missing.status_code == 404


def test_search_endpoint(client):
    """关键字搜索接口。"""
    resp = client.get("/api/search?q=test")
    assert resp.status_code == 200
    assert resp.json["query"] == "test"


def test_comments_page_endpoint(client):
    """评论分页接口（按筛选+排序）。"""
    resp = client.get("/api/comments/page?page=1&sort=likes")
    assert resp.status_code == 200
    assert resp.json["pagination"]["page"] == 1
    assert resp.json["pagination"]["total"] >= 0
    assert len(resp.json["comments"]) <= 30


def test_artist_trend_endpoint(client):
    """艺人热度时间趋势接口。"""
    resp = client.get("/api/analytics/artist-trend?artist=nonexistent-artist")
    assert resp.status_code == 200
    assert resp.json["artist"] == "nonexistent-artist"
    assert isinstance(resp.json["items"], list)
    # 缺少艺人参数时返回空列表
    empty = client.get("/api/analytics/artist-trend")
    assert empty.status_code == 200
    assert empty.json["items"] == []
