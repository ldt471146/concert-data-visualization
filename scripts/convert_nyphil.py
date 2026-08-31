# -*- coding: utf-8 -*-
"""纽约爱乐乐团演出史数据集转换脚本。

数据源：Kaggle 公开数据集 nyphil/perf-history（纽约爱乐 1842 年至今演出历史，CC 许可）。
下载：Kaggle API 直链（需跳过证书吊销检查，Windows schannel 问题）。
输出：统一规整 schema data/raw/nyphil_concerts.csv。

合规说明：数据集公开，转换保留来源 URL 与采集时间。
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys
import warnings
import zipfile
from datetime import date

import requests

warnings.filterwarnings("ignore")

KAGGLE_URL = "https://www.kaggle.com/api/v1/datasets/download/nyphil/perf-history"
OUT = os.path.join("data", "raw", "nyphil_concerts.csv")
HEADERS = ["artist_name", "concert_name", "city", "venue", "show_time",
           "price_text", "sale_status", "source_type", "source_url", "collected_at"]


def download() -> bytes:
    resp = requests.get(KAGGLE_URL, headers={"User-Agent": "Mozilla/5.0"},
                        timeout=300, verify=False)
    resp.raise_for_status()
    return resp.content


def parse_concert_rows(zf: zipfile.ZipFile) -> list[dict]:
    rows = []
    with zf.open("concerts.csv") as handle:
        text = io.TextIOWrapper(handle, encoding="utf-8", errors="ignore")
        reader = csv.reader(text)
        header = next(reader, None)
        if not header:
            return rows
        for line in reader:
            if len(line) < 8:
                continue
            show_time = (line[0] or "").strip()[:10]
            city = (line[1] or "").strip()
            venue = (line[3] or "").strip()
            season = (line[5] or "").strip()
            artist = (line[7] or "").strip()
            concert_name = f"{artist} 演出季 {season}" if season else f"{artist} 音乐会"
            rows.append({
                "artist_name": artist,
                "concert_name": concert_name,
                "city": city,
                "venue": venue,
                "show_time": show_time,
                "price_text": "待定",
                "sale_status": "待定",
                "source_type": "公开数据集",
                "source_url": "https://www.kaggle.com/datasets/nyphil/perf-history",
                "collected_at": date.today().isoformat(),
            })
    return rows


def main() -> None:
    print("downloading nyphil dataset...", flush=True)
    content = download()
    zf = zipfile.ZipFile(io.BytesIO(content))
    rows = parse_concert_rows(zf)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"done: {len(rows)} rows -> {OUT}", flush=True)


if __name__ == "__main__":
    sys.exit(main())