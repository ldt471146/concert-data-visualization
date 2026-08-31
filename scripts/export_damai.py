"""从本地大麦爬虫库 (damai.db) 导出系统演唱会/评论 CSV。

用法:
    python scripts/export_damai.py [db_path] [--out-dir data/raw]

产出:
    data/raw/damai_concerts.csv   —— 全部演出场次(含分类), 与系统 concerts 列兼容
    data/raw/damai_comments.csv   —— 全部评论文本, 与系统 comments 列兼容
    data/raw/damai_prices.csv     —— 票价明细(可选)

数据说明:
    damai.db 为本机大麦网公开爬取结果。comment_info 通过 concert_id 与场次一一对应,
    评论文本是购票/观演者的真实反馈(现场体验、交通、票价等), 与场次天然相关。
    时间跨度: 评价时间 2020-2026, 场次时间 2025-2027。
"""

import argparse
import csv
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def normalize_show_time(raw):
    """把大麦时间文本归一化为主日期 YYYY-MM-DD:
       - 单场: 2026-09-05 19:30 或 2026-09-05
       - 多日: 2026.09.01-10.07 / 2026年8月27日至2026年10月31日 -> 取首日
       - 演出筹备中/时间待定 -> 空(跳过)
    """
    if not raw:
        return ""
    text = str(raw).strip()
    year_first = re.search(r"(20\d{2})", text)
    month = re.search(r"(\d{1,2})月(\d{1,2})日", text) or re.search(r"(\d{1,2})月(\d{1,2})", text)
    if year_first and month:
        year = int(year_first.group(1))
        m, d = int(month.group(1)), int(month.group(2))
        try:
            return datetime(year, m, d).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    dotted = re.match(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", text)
    if dotted:
        y, m, d = int(dotted.group(1)), int(dotted.group(2)), int(dotted.group(3))
        try:
            return datetime(y, m, d).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""


def normalize_price_text(raw):
    if not raw:
        return ""
    text = str(raw)
    parts = re.findall(r"\d+(?:\.\d+)?", text)
    return " / ".join(parts) if parts else text


def normalize_comment_time(raw):
    if not raw:
        return ""
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    m = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)} 00:00:00"
    return text


def export(db_path, out_dir):
    db_path = Path(db_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    concerts_out = out_dir / "damai_concerts.csv"
    comments_out = out_dir / "damai_comments.csv"
    prices_out = out_dir / "damai_prices.csv"

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    with concerts_out.open("w", encoding="utf-8-sig", newline="") as cf, \
         comments_out.open("w", encoding="utf-8-sig", newline="") as mf:
        cw = csv.writer(cf)
        cw.writerow(["artist_name", "concert_name", "city", "venue", "show_time",
                     "price_text", "min_price", "max_price", "sale_status",
                     "source_type", "source_url", "collected_at", "category"])
        mw = csv.writer(mf)
        mw.writerow(["concert_id", "comment_text", "comment_time", "like_count",
                     "user_region", "source_url", "collected_at", "sentiment_score"])

        concerts = cur.execute(
            "SELECT id, project_id, artist_name, concert_name, city, venue, show_time, "
            "price_text, min_price, max_price, sale_status, source_url, category "
            "FROM concert_info ORDER BY id"
        ).fetchall()

        # 场次 id -> 系统内联 id 映射(评论用)
        id_map = {}
        concert_seq = 0
        for row in concerts:
            cid, project_id, artist, name, city, venue, show_time, price_text, mn, mx, status, url, category = row
            show = normalize_show_time(show_time)
            if not show:
                continue  # 无有效日期无法进日历
            artist = (artist or "").strip() or "佚名"
            name = (name or "").strip() or artist
            city = (city or "").strip() or "未知"
            venue = (venue or "").strip() or "未知场地"
            status = (status or "").strip() or "待定"
            price_text = normalize_price_text(price_text)
            try:
                mn_v = float(mn) if mn is not None else (float(re.search(r"\d+(?:\.\d+)?", price_text).group()) if price_text else None)
            except Exception:
                mn_v = None
            try:
                mx_v = float(mx) if mx is not None else mn_v
            except Exception:
                mx_v = mn_v

            concert_seq += 1
            id_map[cid] = concert_seq
            cw.writerow([
                artist, name, city, venue, show, price_text,
                "" if mn_v is None else f"{mn_v:.2f}",
                "" if mx_v is None else f"{mx_v:.2f}",
                status, "爬虫采集",
                url or f"https://detail.damai.cn/item.htm?id={project_id}",
                now, category or "其他演出",
            ])

        comments = cur.execute(
            "SELECT id, concert_id, comment_text, comment_time, like_count, "
            "user_region, source_url, sentiment_score FROM comment_info ORDER BY id"
        ).fetchall()
        for row in comments:
            _cid, concert_id, text, ctime, likes, region, url, senti = row
            if not text or not text.strip():
                continue
            if concert_id not in id_map:
                continue
            ctime = normalize_comment_time(ctime)
            mw.writerow([
                id_map[concert_id],
                text.strip(),
                ctime,
                likes if likes is not None else 0,
                region or "",
                url or "",
                now,
                senti if senti is not None else "",
            ])

    # 票价明细
    with prices_out.open("w", encoding="utf-8-sig", newline="") as pf:
        pw = csv.writer(pf)
        pw.writerow(["concert_id", "price_label", "price", "price_text"])
        detail_rows = cur.execute(
            "SELECT concert_id, price_label, price, price_text FROM ticket_price_detail"
        ).fetchall()
        for cid, label, price, ptext in detail_rows:
            if cid in id_map and price is not None:
                pw.writerow([id_map[cid], label or "", price, ptext or ""])

    conn.close()
    print(f"演唱会: {concert_seq} 场 -> {concerts_out}")
    print(f"评论: {len(comments)} 条 -> {comments_out}")
    print(f"票价明细: {len(detail_rows)} 条 -> {prices_out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="大麦爬虫库导出")
    parser.add_argument("db", nargs="?", default=str(BASE_DIR.parent / "16核16g" / "damai_crawler" / "damai.db"))
    parser.add_argument("--out-dir", default=str(BASE_DIR / "data" / "raw"))
    args = parser.parse_args()
    export(args.db, args.out_dir)