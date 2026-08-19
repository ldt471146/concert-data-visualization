import csv
import re
from pathlib import Path


PRICE_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def normalize_price(text):
    values = [float(item) for item in PRICE_PATTERN.findall(text or "")]
    return (min(values), max(values)) if values else ("", "")


def clean_concert_file(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    seen = set()
    cleaned = []
    for row in rows:
        row = {key: (value or "").strip() for key, value in row.items()}
        name = row.get("concert_name", "")
        city = row.get("city", "")
        venue = row.get("venue", "")
        date = row.get("show_time", "")
        if not name or not city or not venue:
            continue
        key = (name, city, date, venue)
        if key in seen:
            continue
        seen.add(key)
        row["min_price"], row["max_price"] = normalize_price(row.get("price_text", ""))
        cleaned.append(row)
    if cleaned:
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(cleaned[0].keys()))
            writer.writeheader()
            writer.writerows(cleaned)
    return len(rows), len(cleaned)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = clean_concert_file(root / "data/raw/concerts.csv", root / "data/cleaned/concerts.csv")
    print({"input": result[0], "output": result[1]})
