#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并 6 个并行网易云评论分片 + 旧采集 → comments_wyy.csv"""
import csv
from pathlib import Path

FIELDNAMES = ["artist_name", "song_name", "comment_text", "like_count",
              "user_region", "source_url", "collected_at"]
PARTS = [f"data/raw/wyy_part_{i}.csv" for i in range(6)]
OLD = "data/raw/comments_wyy.csv"
OUT = "data/raw/comments_wyy_merged.csv"

def main():
    seen = set()
    rows = []
    files = PARTS + [OLD]
    for rel in files:
        p = Path(rel)
        if not p.exists():
            continue
        with p.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                key = (r.get("artist_name"), r.get("song_name"), r.get("comment_text"))
                if key in seen:
                    continue
                seen.add(key)
                rows.append({k: r.get(k, "") for k in FIELDNAMES})
    out = Path(OUT)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    artists = Counter(r["artist_name"] for r in rows)
    print(f"合并后评论: {len(rows)} 条, {len(artists)} 位艺人", flush=True)

if __name__ == "__main__":
    main()
