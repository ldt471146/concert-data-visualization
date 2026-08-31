"""合并演唱会相关评论：大麦真实场次评论 + B站演唱会视频评论。

产出 data/raw/comments_social_merged.csv:
    concert_name, comment_text, comment_time, like_count, user_region,
    source_platform(bilibili/damai), source_url, collected_at
"""
import csv
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    raw = BASE
    out_rows = []
    seen = set()

    # 1) 大麦演唱会真实场次评论
    damai = read_csv(raw / "social_comments_test.csv")
    for row in damai:
        text = (row.get("comment_text") or "").strip()
        if not text:
            continue
        key = (text, row.get("source_url") or "")
        if key in seen:
            continue
        seen.add(key)
        out_rows.append({
            "concert_name": row.get("concert_name") or "",
            "comment_text": text,
            "comment_time": row.get("comment_time") or "",
            "like_count": row.get("like_count") or 0,
            "user_region": row.get("user_region") or "",
            "source_platform": "damai",
            "source_url": row.get("source_url") or "",
            "collected_at": row.get("collected_at") or "",
        })

    # 2) B站演唱会视频评论（多分片合并）
    parts = sorted(raw.glob("bili_part_*.csv")) + sorted(raw.glob("comments_social*.csv"))
    for path in parts:
        for row in read_csv(path):
            text = (row.get("comment_text") or "").strip()
            if not text:
                continue
            key = (text, row.get("source_url") or "")
            if key in seen:
                continue
            seen.add(key)
            out_rows.append({
                "concert_name": row.get("concert_name") or "",
                "comment_text": text,
                "comment_time": row.get("comment_time") or "",
                "like_count": row.get("like_count") or 0,
                "user_region": row.get("user_region") or "",
                "source_platform": "bilibili",
                "source_url": row.get("source_url") or "",
                "collected_at": row.get("collected_at") or "",
            })

    out = raw / "comments_social_merged.csv"
    fields = ["concert_name", "comment_text", "comment_time", "like_count",
              "user_region", "source_platform", "source_url", "collected_at"]
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    print(f"合并完成: {len(out_rows)} 条 -> {out}")
    from collections import Counter
    print("来源分布:", dict(Counter(r["source_platform"] for r in out_rows)))


if __name__ == "__main__":
    main()