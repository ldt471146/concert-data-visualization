"""从本地大麦爬虫库 (damai.db) 导出【全库有效演出场次 + 全部可挂评论】CSV。

与 export_damai.py（仅演唱会分类）不同，本脚本导出所有 category != '非演出商品' 的场次:
    - 有效演出场次: category in (演唱会/音乐会/音乐节/其他演出/相声喜剧/戏剧/...)  22663 场
    - 评论: 全部能通过 concert_id 挂到有效场次的评论 131574 条 (带大麦自带 sentiment_score)
    - 孤儿评论(concert_id 找不到场次) 排除 —— 系统要求评论必须挂在场次下
"""

import argparse
import csv
import re
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
EXCLUDED_CATEGORY = "非演出商品"


def normalize_show_time(raw):
    if not raw:
        return ""
    text = str(raw).strip()
    month = re.search(r"(\d{1,2})月(\d{1,2})日", text) or re.search(r"(\d{1,2})月(\d{1,2})", text)
    year_first = re.search(r"(20\d{2})", text)
    if year_first and month:
        y, m, d = int(year_first.group(1)), int(month.group(1)), int(month.group(2))
        try:
            return datetime(y, m, d).strftime("%Y-%m-%d")
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


def parse_prices(raw):
    if not raw:
        return None, None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(raw)) if float(x) > 0]
    if not nums:
        return None, None
    return min(nums), max(nums)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", nargs="?", default=r"E:\16核16g\damai_crawler\damai.db")
    ap.add_argument("--out-dir", default=str(BASE_DIR / "data" / "raw"))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(args.db_path)
    db.row_factory = sqlite3.Row

    # 有效场次 = 排除非演出商品
    shows = db.execute(
        "SELECT * FROM concert_info WHERE category != ? ORDER BY id", (EXCLUDED_CATEGORY,)
    ).fetchall()
    print(f"有效场次: {len(shows)}")

    # 评论只保留能挂到有效场次的 (concert_id -> concert_name 映射)
    name_by_id = {r["id"]: r["concert_name"] for r in shows}
    comments = db.execute("SELECT * FROM comment_info ORDER BY id").fetchall()
    keep = [c for c in comments if c["concert_id"] in name_by_id]
    print(f"评论: 总 {len(comments)} -> 可挂有效场次 {len(keep)} (孤儿 {len(comments)-len(keep)} 排除)")

    # 场次 CSV
    concert_path = out_dir / "damai_full_concerts.csv"
    with concert_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["artist_name", "category", "concert_name", "city", "venue", "show_time",
                    "price_text", "min_price", "max_price", "sale_status", "source_type",
                    "source_url", "collected_at"])
        for r in shows:
            mn, mx = parse_prices(r["price_text"])
            w.writerow([
                r["artist_name"] or "群星",
                r["category"] or "演唱会",
                r["concert_name"],
                r["city"] or "未知",
                r["venue"] or "未知场地",
                normalize_show_time(r["show_time"]),
                r["price_text"] or "",
                f"{mn:.2f}" if mn is not None else "",
                f"{mx:.2f}" if mx is not None else "",
                r["sale_status"] or "待定",
                "爬虫采集-大麦",
                r["source_url"] or "",
                r["collected_at"] or "",
            ])
    print(f"场次 CSV: {concert_path} ({len(shows)} 行)")

    # 评论 CSV (带 sentiment_score, 用 project_id 标注场次归属, 导入时按 concert_name 关联)
    comment_path = out_dir / "damai_full_comments.csv"
    with comment_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["concert_name", "comment_text", "comment_time", "like_count",
                    "user_region", "source_url", "collected_at", "sentiment_score"])
        for c in keep:
            w.writerow([
                name_by_id.get(c["concert_id"], ""),
                c["comment_text"] or "",
                c["comment_time"] or "",
                c["like_count"] or 0,
                c["user_region"] or "",
                c["source_url"] or "",
                c["collected_at"] or "",
                c["sentiment_score"] if c["sentiment_score"] is not None else "",
            ])
    print(f"评论 CSV: {comment_path} ({len(keep)} 行)")


if __name__ == "__main__":
    main()