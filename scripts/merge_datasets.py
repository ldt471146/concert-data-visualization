# -*- coding: utf-8 -*-
"""多种来源演唱会数据合并去重脚本。

来源：
- data/raw/concerts.csv            已有 9 来源快照（爬虫采集）
- data/raw/musicbrainz_events.csv  MusicBrainz 演唱会事件（公开数据集）
- data/raw/nyphil_concerts.csv     纽约爱乐演出史（公开数据集）
- data/raw/showstart_concerts.csv  秀动网演出（爬虫采集）

输出：
- data/raw/concerts_merged.csv     合并去重后的原始快照（保留各来源字段）
- data/raw/merge_stats.txt         各来源数量、去重后总量与来源分布

去重指纹：（artist_name, concert_name, venue, show_time 前 10 位日期）
重复记录保留首个来源，并在文档中分别统计来源数量。
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

SOURCES = [
    ("data/raw/concerts.csv", "爬虫采集"),
    ("data/raw/musicbrainz_events.csv", "公开数据集"),
    ("data/raw/nyphil_concerts.csv", "公开数据集"),
    ("data/raw/showstart_concerts.csv", "爬虫采集"),
]
OUT = "data/raw/concerts_merged.csv"
STATS = "data/raw/merge_stats.txt"
HEADERS = ["artist_name", "concert_name", "city", "venue", "show_time",
           "price_text", "sale_status", "source_type", "source_url", "collected_at"]


def read_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def make_key(row: dict) -> str:
    artist = (row.get("artist_name") or "").strip()
    name = (row.get("concert_name") or "").strip()
    venue = (row.get("venue") or "").strip()
    date = (row.get("show_time") or "").strip()[:10]
    return "|".join([artist, name, venue, date])


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    seen: dict[str, dict] = {}
    source_counts: Counter = Counter()
    source_rows: Counter = Counter()

    for rel, label in SOURCES:
        path = root / rel
        if not path.exists():
            print(f"跳过（不存在）：{rel}", flush=True)
            continue
        rows = read_rows(path)
        source_rows[label] = len(rows)
        for row in rows:
            row = {key: (row.get(key) or "").strip() for key in HEADERS}
            if not row.get("concert_name"):
                continue
            key = make_key(row)
            if key not in seen:
                seen[key] = row
                source_counts[label + "（去重后）"] += 1

    out_path = root / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(seen.values())

    stats = []
    stats.append(f"各来源原始行数：{dict(source_rows)}")
    stats.append(f"来源去重后贡献：{dict(source_counts)}")
    stats.append(f"合并去重后总量（原始快照）：{len(seen)}")
    artists = Counter(r["artist_name"] for r in seen.values() if r["artist_name"])
    cities = Counter(r["city"] for r in seen.values() if r["city"])
    stats.append(f"去重后艺人数量：{len(artists)}")
    stats.append(f"去重后城市数量：{len(cities)}")
    with (root / STATS).open("w", encoding="utf-8") as handle:
        handle.write("\n".join(stats) + "\n")

    print("\n".join(stats), flush=True)


if __name__ == "__main__":
    main()