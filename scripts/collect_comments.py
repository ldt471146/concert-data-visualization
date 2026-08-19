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
    text = soup.get_text(" ", strip=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["concert_name", "comment_text", "comment_time", "like_count", "user_region", "source_url", "collected_at"])
        writer.writeheader()
        writer.writerow({"concert_name": "", "comment_text": text[:500], "comment_time": "", "like_count": 0, "user_region": "", "source_url": url, "collected_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")})
    return len(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="读取允许访问的公开静态页面并保存评论原始快照")
    parser.add_argument("url")
    parser.add_argument("--output", default="data/raw/comment_snapshot.csv")
    args = parser.parse_args()
    print({"characters": collect(args.url, Path(args.output))})
