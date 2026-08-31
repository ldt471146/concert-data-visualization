#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云评论 → 系统评论CSV 转换脚本
================================================================
读   : data/raw/comments_wyy_merged.csv  (artist_name, song_name, comment_text,
       like_count, user_region, source_url, collected_at)
     : data/raw/concerts_merged.csv (艺人→演唱会映射)
写   : data/raw/comments_input.csv (系统导入格式:
       concert_name, comment_text, comment_time, like_count, user_region,
       source_url, collected_at)
策略: 评论按艺人名关联到该艺人的某场演唱会; 无对应艺人时跳过
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

WYY = "data/raw/comments_wyy_merged.csv"
MERGED = "data/raw/concerts_merged.csv"
OUT = "data/raw/comments_input.csv"

FIELDNAMES = ["concert_name", "comment_text", "comment_time",
              "like_count", "user_region", "source_url", "collected_at"]


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", (name or "")).lower()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    wyy_path = root / WYY
    merged_path = root / MERGED
    if not wyy_path.exists() or not merged_path.exists():
        print("缺少输入文件", flush=True)
        return

    # 艺人 → 演唱会列表（归一化匹配）
    artist_concerts: dict[str, list[str]] = defaultdict(list)
    with merged_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            artist = _norm(row.get("artist_name"))
            if artist:
                artist_concerts[artist].append(row.get("concert_name", ""))

    total, matched, skipped = 0, 0, 0
    with wyy_path.open(encoding="utf-8-sig", newline="") as fin, \
         (root / OUT).open("w", encoding="utf-8-sig", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in csv.DictReader(fin):
            total += 1
            text = (row.get("comment_text") or "").strip()
            if not text:
                continue
            artist = _norm(row.get("artist_name"))
            concerts = artist_concerts.get(artist)
            if not concerts:
                skipped += 1
                continue
            writer.writerow({
                "concert_name": concerts[0],
                "comment_text": text[:2000],
                "comment_time": "",
                "like_count": row.get("like_count") or 0,
                "user_region": "",
                "source_url": row.get("source_url") or "local://data/raw/comments_wyy_merged.csv",
                "collected_at": row.get("collected_at") or "",
            })
            matched += 1
        # 回退：那些艺人不在 merged 的，散落到“未知艺人”场次？不，跳过即可
    print(f"总评论 {total}, 关联成功 {matched}, 跳过 {skipped}, 输出 {OUT}", flush=True)


if __name__ == "__main__":
    main()
