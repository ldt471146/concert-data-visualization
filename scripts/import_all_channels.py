"""全量数据重建: 大麦全库有效场次 + 三渠道评论 (大麦/网易云/B站)。

- 场次: data/raw/damai_full_concerts.csv (22663 场, 排除非演出商品, 分类保留)
- 评论: damai_full_comments.csv (大麦场次真实评论) + comments_wyy_merged.csv
        (网易云按歌手关联) + comments_social_merged.csv (B站演唱会视频评论)
- 网易云歌手名清洗后与库内艺人匹配; B站按 concert_name 前缀匹配艺人
"""

import csv
import re
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "instance" / "pulse_atlas.db"
RAW = BASE_DIR / "data" / "raw"


def parse_dt(v):
    if not v:
        return None
    v = str(v).strip()
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(v[:19], f)
        except ValueError:
            continue
    return None


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA synchronous=OFF")

    # ===== 场次 (全库有效演出) =====
    rows = list(csv.DictReader((RAW / "damai_full_concerts.csv").open(encoding="utf-8-sig")))
    concert_batch = []
    for r in rows:
        t = parse_dt(r["show_time"])
        if not t or t.year > 2028:  # 过滤 2034 等异常
            continue
        concert_batch.append((
            r["artist_name"] or "群星", r["category"] or "演唱会", r["concert_name"],
            r["city"] or "未知", r["venue"] or "未知场地", t.isoformat(sep=" "),
            r["price_text"] or "", float(r["min_price"]) if r["min_price"] else None,
            float(r["max_price"]) if r["max_price"] else None, r["sale_status"] or "待定",
            r["source_url"] or "", r["source_type"] or "爬虫采集-大麦",
            parse_dt(r["collected_at"]) or datetime.now(), datetime.now().isoformat(sep=" "),
        ))
    conn.executemany(
        """INSERT OR IGNORE INTO concert_info
           (artist_name, category, concert_name, city, venue, show_time, price_text,
            min_price, max_price, sale_status, source_url, source_type, collected_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        concert_batch,
    )
    conn.commit()
    print(f"场次导入: {len(concert_batch)}")

    # 艺人名 -> 首选场次id (评论关联)
    artist_first = {}
    name_id = {}
    for row in conn.execute("SELECT id, artist_name, concert_name FROM concert_info"):
        name_id.setdefault(row[2], row[0])
        artist_first.setdefault(row[1], row[0])

    def insert_comments(source, rows_iter, match_mode):
        """match_mode: 'exact_concert' 按场次名精确 / 'artist' 按艺人名"""
        batch = []
        seen = set()
        miss = 0
        for r in rows_iter:
            text = (r.get("comment_text") or "").strip()
            if not text:
                continue
            if match_mode == "exact_concert":
                cid = name_id.get(r.get("concert_name") or "")
            else:
                cid = artist_first.get((r.get("artist_name") or "").strip())
            if cid is None:
                miss += 1
                continue
            key = (cid, text[:200])
            if key in seen:
                continue
            seen.add(key)
            batch.append((
                cid, text, parse_dt(r.get("comment_time")),
                int(float(r.get("like_count") or 0)), r.get("user_region") or "",
                r.get("source_url") or "", parse_dt(r.get("collected_at")) or datetime.now(),
                None,
            ))
        print(f"[{source}] 待插入: {len(batch)} (未匹配: {miss})")
        conn.executemany(
            """INSERT OR IGNORE INTO comment_info
               (concert_id, comment_text, comment_time, like_count, user_region,
                source_url, collected_at, sentiment_score)
               VALUES (?,?,?,?,?,?,?,?)""",
            batch,
        )
        conn.commit()
        return len(batch)

    # ===== 评论: 大麦 (带情感分) =====
    crows = list(csv.DictReader((RAW / "damai_full_comments.csv").open(encoding="utf-8-sig")))
    crows = [r for r in crows if name_id.get(r.get("concert_name") or "")]
    batch = []
    seen = set()
    for r in crows:
        text = (r.get("comment_text") or "").strip()
        if not text:
            continue
        cid = name_id[r["concert_name"]]
        key = (cid, text[:200])
        if key in seen:
            continue
        seen.add(key)
        batch.append((
            cid, text, parse_dt(r.get("comment_time")),
            int(float(r.get("like_count") or 0)), r.get("user_region") or "",
            r.get("source_url") or "", parse_dt(r.get("collected_at")) or datetime.now(),
            float(r["sentiment_score"]) if r.get("sentiment_score") else None,
        ))
    conn.executemany(
        """INSERT OR IGNORE INTO comment_info
           (concert_id, comment_text, comment_time, like_count, user_region,
            source_url, collected_at, sentiment_score)
           VALUES (?,?,?,?,?,?,?,?)""",
        batch,
    )
    conn.commit()
    print(f"[damai] 评论导入: {len(batch)}")

    # ===== 评论: 网易云 (按清洗后歌手匹配) =====
    def norm_artist(a):
        a = re.sub(r"^\d{1,2}\.\d{1,2}-\d{1,2}\.\d{1,2}", "", a or "")
        a = re.sub(r"\s+.*$", "", a)
        return a.strip()

    wyy = list(csv.DictReader((RAW / "comments_wyy_merged.csv").open(encoding="utf-8-sig")))
    for r in wyy:
        r["artist_name"] = norm_artist(r.get("artist_name"))
    insert_comments("wyy", wyy, "artist")

    # ===== 评论: B站 (concer_name 前缀匹配艺人) =====
    bili = list(csv.DictReader((RAW / "comments_social_merged.csv").open(encoding="utf-8-sig")))
    bili_artist_dict = {}
    for r in bili:
        artist_key = None
        for a in artist_first:
            if (r.get("concert_name") or "").startswith(a):
                artist_key = a
                break
        bili_artist_dict[id(r)] = artist_key
    # 注入 artist_name 便于统一导入
    for r in bili:
        r["artist_name"] = bili_artist_dict.get(id(r))
    insert_comments("bili", bili, "artist")

    print("完成:", conn.execute("SELECT COUNT(*) FROM concert_info").fetchone()[0],
          "场 /", conn.execute("SELECT COUNT(*) FROM comment_info").fetchone()[0], "评论")
    conn.close()


if __name__ == "__main__":
    main()