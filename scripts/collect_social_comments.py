"""多平台演唱会相关评论采集：B站公开评论 API（wbi 签名，无需登录）。

来源说明（论文用）:
- source_platform: "bilibili" —— B站公开接口 api.bilibili.com/x/v2/reply/main
- source_platform: "damai"     —— 本地大麦爬虫库演唱会分类场次评论
- source_url: 每条评论对应的视频页/场次页地址，可复核

用法:
    python scripts/collect_social_comments.py --out data/raw/social_comments.csv [--max-per-artist 40] [--artists "薛之谦,周杰伦"...]
"""

import argparse
import random
import csv
import hashlib
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, r"E:\16核16g\damai_crawler")
from curl_cffi import requests as creq

BASE_DIR = Path(__file__).resolve().parents[1]

MIXIN_KEY_ENC_TAB = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]

_session = creq.Session(impersonate="chrome120")
_wbi_key = None


def _reset_session():
    """重建会话并刷新 wbi 密钥（B站风控后使用）。"""
    global _session, _wbi_key
    _session = creq.Session(impersonate="chrome120")
    try:
        _session.get("https://www.bilibili.com/", timeout=10)
    except Exception:
        pass
    _wbi_key = None
    try:
        _get_wbi_key()
    except Exception:
        pass


def _get_wbi_key():
    global _wbi_key
    if _wbi_key:
        return _wbi_key
    r = _session.get("https://api.bilibili.com/x/web-interface/nav", timeout=15)
    data = r.json().get("data", {})
    img = (data.get("wbi_img", {}).get("img_url") or "").split("/")[-1].split(".")[0]
    sub = (data.get("wbi_img", {}).get("sub_url") or "").split("/")[-1].split(".")[0]
    _wbi_key = img + sub
    return _wbi_key


def _wbi_sign(params):
    key = _get_wbi_key()
    salted = "".join(key[i] for i in MIXIN_KEY_ENC_TAB)[:32]
    params["wts"] = int(time.time())
    query = urllib.parse.urlencode(params)
    params["w_rid"] = hashlib.md5((query + salted).encode()).hexdigest()
    return params


def bili_search_videos(keyword, page=1, limit=5):
    """搜索 B 站演唱会相关视频，返回 [{bvid, aid, title, author, play}]。

    先取搜索会话票据 v_voucher，再用完整网页端参数搜索（缺参会返回空 result）。
    B 站搜索风控不稳定，失败时重建会话与 wbi 密钥重试。
    """
    base = {
        "search_type": "video", "keyword": keyword, "page": page,
        "page_size": 20, "order": "", "duration": "",
        "tids_1": "", "tids_2": "",
        "platform": "pc", "from_source": "webtop_search",
        "spm_id_from": "333.1007",
    }
    try:
        # 步骤1: 拿 v_voucher
        r0 = _session.get(
            "https://api.bilibili.com/x/web-interface/wbi/search/type",
            params=_wbi_sign({**base}), timeout=15,
        )
        voucher = (r0.json().get("data") or {}).get("v_voucher")
        if voucher:
            base["v_voucher"] = voucher
        # 步骤2: 正式搜索
        params = _wbi_sign(base)
        r = _session.get(
            "https://api.bilibili.com/x/web-interface/wbi/search/type",
            params=params, timeout=15,
        )
        j = r.json()
        results = (j.get("data") or {}).get("result") or []
        # 空结果/风控: 重置会话重试
        for attempt in range(4):
            if results:
                break
            time.sleep(3 + attempt * 3)
            _reset_session()
            r0 = _session.get(
                "https://api.bilibili.com/x/web-interface/wbi/search/type",
                params=_wbi_sign({**base}), timeout=15,
            )
            voucher = (r0.json().get("data") or {}).get("v_voucher")
            if voucher:
                base["v_voucher"] = voucher
            params = _wbi_sign(base)
            r = _session.get(
                "https://api.bilibili.com/x/web-interface/wbi/search/type",
                params=params, timeout=15,
            )
            results = (r.json().get("data") or {}).get("result") or []
        out = []
        for v in results[:limit]:
            aid = v.get("aid") or v.get("id")
            out.append({
                "bvid": v.get("bvid"),
                "aid": aid,
                "title": re.sub(r"<[^>]+>", "", v.get("title") or ""),
                "author": v.get("author") or "",
                "play": v.get("play") or 0,
            })
        return out
    except Exception as exc:
        print(f"[bili] 搜索失败 {keyword}: {exc}", flush=True)
        try:
            print(f"[bili] 搜索返回: {r.text[:200]}", flush=True)
        except Exception:
            pass
        return []


def bili_fetch_comments(aid, max_pages=5):
    """抓取视频热评（前 max_pages 页，每页 20 条），返回评论列表。"""
    if not aid:
        return []
    comments = []
    for pn in range(1, max_pages + 1):
        try:
            params = _wbi_sign({
                "type": 1, "oid": aid, "mode": 3, "pn": pn, "ps": 20, "plat": 1,
                "web_location": 1315875,
            })
            r = _session.get("https://api.bilibili.com/x/v2/reply/main", params=params, timeout=15)
            j = r.json()
            replies = (j.get("data") or {}).get("replies") or []
            for rep in replies:
                content = rep.get("content", {})
                text = content.get("message") if isinstance(content, dict) else str(content)
                member = rep.get("member", {})
                comments.append({
                    "text": (text or "").strip(),
                    "like": rep.get("like") or 0,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime((rep.get("ctime") or 0))),
                    "region": member.get("location") or member.get("level_info", {}).get("level", ""),
                    "reply_id": rep.get("rpid") or "",
                })
            if len(replies) < 20:
                break
            time.sleep(0.5)
        except Exception as exc:
            print(f"[bili] 评论失败 aid={aid}: {exc}", flush=True)
            break
    return comments


def export_damai_concert_comments(out_path):
    """大麦库演唱会分类场次 + 其真实评论。"""
    import sqlite3
    conn = sqlite3.connect(r"E:\16核16g\damai_crawler\damai.db")
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, project_id, artist_name, concert_name, city, venue, show_time, "
        "price_text, min_price, max_price, sale_status, source_url "
        "FROM concert_info WHERE category='演唱会' ORDER BY id"
    ).fetchall()
    concerts = []
    id_map = {}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for r in rows:
        cid, pid, artist, name, city, venue, show, price, mn, mx, status, url = r
        show_n = _normalize_show(show)
        if not show_n:
            continue
        concerts.append({
            "artist_name": (artist or "").strip() or "佚名",
            "concert_name": (name or "").strip() or (artist or ""),
            "city": (city or "").strip() or "未知",
            "venue": (venue or "").strip() or "未知场地",
            "show_time": show_n,
            "price_text": _normalize_price(price),
            "sale_status": (status or "").strip() or "待定",
            "source_type": "爬虫采集-大麦",
            "source_url": url or f"https://detail.damai.cn/item.htm?id={pid}",
            "collected_at": now,
        })
        id_map[cid] = len(concerts) - 1

    comments = []
    for r in cur.execute(
        "SELECT concert_id, comment_text, comment_time, like_count, user_region, source_url "
        "FROM comment_info ORDER BY id"
    ).fetchall():
        cid, text, ctime, likes, region, url = r
        if cid not in id_map or not text or not text.strip():
            continue
        comments.append({
            "concert_name": concerts[id_map[cid]]["concert_name"],
            "comment_text": text.strip(),
            "comment_time": _normalize_ctime(ctime),
            "like_count": likes or 0,
            "user_region": region or "",
            "source_platform": "damai",
            "source_url": url or concerts[id_map[cid]]["source_url"],
            "collected_at": now,
        })
    conn.close()

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(comments[0].keys()) if comments else
                           ["concert_name", "comment_text", "comment_time", "like_count",
                            "user_region", "source_platform", "source_url", "collected_at"])
        w.writeheader()
        for c in comments:
            w.writerow(c)
    print(f"[damai] 演唱会场次 {len(concerts)} 场, 评论 {len(comments)} 条 -> {out_path}", flush=True)
    return concerts, comments


def _normalize_show(raw):
    if not raw:
        return ""
    text = str(raw).strip()
    m = re.match(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", text)
    if m:
        try:
            import datetime
            return datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    yr = re.search(r"(20\d{2})", text)
    mo = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if yr and mo:
        try:
            import datetime
            return datetime.datetime(int(yr.group(1)), int(mo.group(1)), int(mo.group(2))).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""


def _normalize_price(raw):
    if not raw:
        return ""
    parts = re.findall(r"\d+(?:\.\d+)?", str(raw))
    return " / ".join(parts) if parts else str(raw)


def _normalize_ctime(raw):
    if not raw:
        return ""
    text = str(raw).strip()
    m = re.search(r"(20\d{2}-\d{1,2}-\d{1,2})", text)
    return m.group(1) + " " + (re.search(r"\d{2}:\d{2}", text).group() if re.search(r"\d{2}:\d{2}", text) else "00:00:00")


def main():
    parser = argparse.ArgumentParser(description="B站演唱会评论采集")
    parser.add_argument("--out", default=str(BASE_DIR / "data" / "raw" / "social_comments.csv"))
    parser.add_argument("--artists", default="", help="逗号分隔艺人名单, 默认用大麦演唱会艺人")
    parser.add_argument("--artists-file", default="", help="艺人名单文件(每行一个), 优先于 --artists")
    parser.add_argument("--max-per-artist", type=int, default=30)
    parser.add_argument("--max-artists", type=int, default=200)
    args = parser.parse_args()

    out_path = Path(args.out)

    # 大麦演唱会主体 + 评论（仅当未指定 --artists 时，避免并行分片重复导出）
    if args.artists_file:
        concerts, damai_comments = [], []
        artists = [l.strip() for l in Path(args.artists_file).read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"[bili] 按文件采集 {len(artists)} 位艺人（跳过导出）", flush=True)
    elif args.artists:
        concerts, damai_comments = [], []
        artists = [a.strip() for a in args.artists.split(",") if a.strip()]
        print(f"[bili] 按名单采集 {len(artists)} 位艺人（跳过导出）", flush=True)
    else:
        concerts, damai_comments = export_damai_concert_comments(out_path)
        seen = set()
        artists = []
        for c in concerts:
            name = c["artist_name"]
            if name not in seen:
                seen.add(name)
                artists.append(name)
        artists = artists[: args.max_artists]
        print(f"[bili] 待搜索艺人 {len(artists)} 位", flush=True)

    bili_comments = []
    rows_out = []
    for artist in artists:
        keyword = f"{artist} 演唱会"
        videos = bili_search_videos(keyword, limit=3)
        videos += bili_search_videos(keyword, page=2, limit=1)
        videos += bili_search_videos(keyword, page=3, limit=1)
        if not videos:
            print(f"[bili] {artist}: 无视频", flush=True)
            continue
        got = 0
        for video in videos:
            comments = bili_fetch_comments(video["aid"], max_pages=2)
            for c in comments:
                rows_out.append({
                    "concert_name": f"{artist} 演唱会相关视频评论",
                    "comment_text": c["text"],
                    "comment_time": c["time"],
                    "like_count": c["like"],
                    "user_region": c["region"],
                    "source_platform": "bilibili",
                    "source_url": f"https://www.bilibili.com/video/{video['bvid']}",
                    "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })
                got += 1
                bili_comments.append(c)
            if got >= args.max_per_artist:
                break
            time.sleep(0.4)
        print(f"[bili] {artist}: {got} 条", flush=True)
        time.sleep(5 + random.random() * 3)

    # 合并写出
    fieldnames = ["concert_name", "comment_text", "comment_time", "like_count",
                  "user_region", "source_platform", "source_url", "collected_at"]
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for c in damai_comments:
            w.writerow(c)
        for r in rows_out:
            w.writerow(r)
    print(f"\n合计: 大麦 {len(damai_comments)} + B站 {len(rows_out)} = {len(damai_comments) + len(rows_out)} 条 -> {out_path}", flush=True)


if __name__ == "__main__":
    main()