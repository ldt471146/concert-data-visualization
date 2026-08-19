import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


def collect(url, output):
    response = requests.get(url, timeout=15, headers={"User-Agent": "PulseAtlasStudy/1.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "公开页面快照"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["artist_name", "concert_name", "city", "venue", "show_time", "price_text", "sale_status", "source_url", "collected_at"])
        writer.writeheader()
        writer.writerow({"artist_name": "", "concert_name": title, "city": "", "venue": "", "show_time": "", "price_text": "", "sale_status": "待人工核对", "source_url": url, "collected_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")})
    return title


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="读取允许访问的公开静态页面并保存最小原始快照")
    parser.add_argument("url")
    parser.add_argument("--output", default="data/raw/page_snapshot.csv")
    args = parser.parse_args()
    print(collect(args.url, Path(args.output)))
