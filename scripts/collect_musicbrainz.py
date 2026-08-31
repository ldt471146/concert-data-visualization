# -*- coding: utf-8 -*-
"""MusicBrainz 演唱会事件采集脚本。

数据源：MusicBrainz（开源音乐数据库，CC0 许可，公开数据，无需登录）。
采集方式：Web Service API 分页搜索 type:Concert 事件，约 8 万余条。

合规说明：
- 使用合规 User-Agent 标识来源项目。
- 尊重 MusicBrainz 限速要求（1 request/s），失败重试、429 退避。
- 不绕过验证码、不访问受限接口。
"""
from __future__ import annotations

import csv
import os
import sys
import time
from datetime import date

import requests

API = "https://musicbrainz.org/ws/2/event"
UA = "PulseAtlasResearch/0.1 (graduation-project; contact: panglijuan@example.com)"
OUT = os.path.join("data", "raw", "musicbrainz_events.csv")
STATS = os.path.join("data", "raw", "musicbrainz_stats.txt")
HEADERS = ["artist_name", "concert_name", "city", "venue", "show_time",
           "price_text", "sale_status", "source_type", "source_url", "collected_at"]


def fetch(offset: int, session: requests.Session) -> dict:
    for attempt in range(6):
        try:
            resp = session.get(
                API,
                params={
                    "query": "*",
                    "fmt": "json",
                    "limit": 100,
                    "offset": offset,
                    "inc": "artist-rels+place-rels+url-rels",
                },
                timeout=60,
            )
            if resp.status_code == 429:
                time.sleep(15)
                continue
            if resp.status_code == 503:
                # 服务器繁忙：退避重试，不退避过久
                time.sleep(10 + attempt * 8)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            time.sleep(8)
            continue
        except Exception as exc:  # noqa: BLE001
            wait = 2 ** attempt
            time.sleep(wait)
            if attempt == 5:
                raise RuntimeError(f"offset={offset} 失败: {exc}") from exc
    return {}


def extract_event(event: dict) -> dict:
    name = (event.get("name") or "").strip()
    lifespan = event.get("life-span") or {}
    begin = (lifespan.get("begin") or "").strip()

    artist, venue = "", ""
    for rel in event.get("relations", []):
        if "artist" in rel:
            rtype = rel.get("type", "")
            artist_name = (rel.get("artist") or {}).get("name", "")
            if rtype in ("main performer", "performer") and not artist:
                artist = artist_name
        elif "place" in rel:
            rtype = rel.get("type", "")
            place_name = (rel.get("place") or {}).get("name", "")
            if rtype == "held at" and not venue:
                venue = place_name

    if not artist:
        for rel in event.get("relations", []):
            if "artist" in rel and not artist:
                artist = (rel.get("artist") or {}).get("name", "")

    return {
        "artist_name": artist,
        "concert_name": name,
        "city": "",
        "venue": venue,
        "show_time": begin,
        "price_text": "待定",
        "sale_status": "待定",
        "source_type": "公开数据集",
        "source_url": "https://musicbrainz.org/doc/MusicBrainz_Database",
        "collected_at": date.today().isoformat(),
    }


def main() -> None:
    session = requests.Session()
    session.headers["User-Agent"] = UA

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    total = None
    rows_written = 0
    offset = 0
    start = time.time()

    # 断电续抓：已有文件则从已写行数继续（每 100 条一批）
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8-sig", newline="") as handle:
            existing = sum(1 for _ in handle) - 1
        if existing > 0:
            offset = existing - (existing % 100)
            if offset < existing:
                offset += 100
            rows_written = offset
            print(f"resume from offset={offset} (已有 {existing} 行)", flush=True)
    with open(OUT, "a", encoding="utf-8-sig", newline="") as handle:
        if offset == 0:
            # 新建文件时写表头
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
        writer = csv.DictWriter(handle, fieldnames=HEADERS, extrasaction="ignore")
        while total is None or offset < total:
            try:
                data = fetch(offset, session)
            except RuntimeError:
                print(f"offset={offset} 终止", flush=True)
                break
            events = data.get("events", [])
            if not events:
                break
            if total is None:
                total = data.get("count")
                print(f"total events: {total}", flush=True)
            for event in events:
                writer.writerow(extract_event(event))
            rows_written += len(events)
            offset += len(events)
            if offset % 1000 == 0:
                elapsed = time.time() - start
                print(f"progress: {rows_written}/{total} ({elapsed:.0f}s)", flush=True)
            time.sleep(1.05)

    print(f"done: {rows_written} rows, {time.time()-start:.0f}s", flush=True)

    artists = set()
    with open(OUT, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["artist_name"]:
                artists.add(row["artist_name"])
    with open(STATS, "w", encoding="utf-8") as handle:
        handle.write(f"rows={rows_written}\n")
        handle.write(f"distinct_artists={len(artists)}\n")
        handle.write(f"source=MusicBrainz (CC0)\n")
        handle.write(f"collected_at={date.today().isoformat()}\n")
    print(f"stats: rows={rows_written} artists={len(artists)}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
