#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网易云音乐歌曲评论采集脚本（公开评论接口，无需登录）
================================================================
数据源 : music.163.com 公开评论接口
  - 搜索歌手: /api/search/get?s={artist}&type=100
  - 热门歌曲: /api/artist/top/song?id={artist_id}
  - 热评列表: /api/v1/resource/comments/R_SO_4_{song_id}?limit=50&offset=0
采集策略:
  - 低频: 每个请求间隔 >= 1.2 秒; 失败重试 2 次
  - UA + Referer 模拟浏览器; 不做登录/验证码/反爬绕过
  - 评论均为网易云用户公开评论, 用于情感分析/词频分析
输出   : data/raw/comments_wyy.csv (UTF-8 with BOM)
列     : artist_name, song_name, comment_text, like_count, user_region,
         source_url, collected_at
"""

import csv
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

BASE = "https://music.163.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://music.163.com/",
    "Accept": "application/json, text/plain, */*",
}

FIELDNAMES = [
    "artist_name", "song_name", "comment_text", "like_count",
    "user_region", "source_url", "collected_at",
]


def _get(url, params=None, retries=2):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2 + attempt * 2)
    return None


def _is_noise_artist(name: str) -> bool:
    """过滤日期前缀/单口喜剧/互动/超长英文等非艺人名噪声"""
    if not name:
        return True
    if re.search(r"\d{1,2}月|\d{1,2}日|单口|脱口秀|互动|巡游|烟花秀|灯光秀", name):
        return True
    if len(name) > 25:
        return True
    return False


def _load_artists(path="data/raw/piaoniu_concerts.csv", limit=None):
    """从票牛采集结果里收集艺人名单（去重）"""
    p = Path(path)
    if not p.exists():
        return []
    artists = set()
    with p.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("artist_name") or "").strip()
            if name and not _is_noise_artist(name):
                artists.add(name)
    # 补充秀动艺人
    p2 = Path("data/raw/showstart_concerts.csv")
    if p2.exists():
        with p2.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                name = (row.get("artist_name") or "").strip()
                if name and not _is_noise_artist(name):
                    artists.add(name)
    ordered = sorted(artists)
    return ordered[:limit] if limit else ordered


def _search_artist(name):
    d = _get(BASE + "/api/search/get", {"s": name, "type": 100, "limit": 5})
    if not d:
        return None
    artists = (d.get("result") or {}).get("artists") or []
    if not artists:
        return None
    return artists[0]


def _artist_top_songs(artist_id, limit=8):
    d = _get(BASE + "/api/artist/top/song", {"id": artist_id, "limit": limit})
    if not d:
        return []
    return [
        {"id": s.get("id"), "name": s.get("name")}
        for s in (d.get("songs") or [])
        if s.get("id")
    ][:limit]


def _song_hot_comments(song_id, pages=3):
    """每首歌翻 pages 页(每页15条)热门评论, 低频控制"""
    out = []
    for offset in range(0, 15 * pages, 15):
        d = _get(
            BASE + f"/api/v1/resource/comments/R_SO_4_{song_id}",
            {"limit": 15, "offset": offset},
        )
        if not d:
            continue
        chunk = d.get("hotComments") or []
        if not chunk:
            break
        for c in chunk:
            out.append({
                "text": (c.get("content") or "").strip().replace("\n", " "),
                "likes": c.get("likedCount") or 0,
                "nick": (c.get("user") or {}).get("nickname") or "",
                "time": c.get("time"),
            })
        time.sleep(1.0)
    return out


def collect(artists, max_songs=4, per_song=45, out_path="data/raw/comments_wyy.csv"):
    out = Path(out_path)
    done_artists = set()
    if out.exists():
        with out.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                done_artists.add(row.get("artist_name", ""))

    total = 0
    with out.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        if out.stat().st_size == 0:
            writer.writeheader()
        for artist in artists:
            if artist in done_artists:
                continue
            ainfo = _search_artist(artist)
            if not ainfo:
                print(f"  {artist}: 歌手未找到, 跳过", flush=True)
                continue
            songs = _artist_top_songs(ainfo.get("id"), max_songs)
            if not songs:
                print(f"  {artist}: 无热门歌曲, 跳过", flush=True)
                continue
            time.sleep(1.2)
            for song in songs:
                comments = _song_hot_comments(song["id"], per_song)
                for cm in comments:
                    writer.writerow({
                        "artist_name": artist,
                        "song_name": song["name"],
                        "comment_text": cm["text"],
                        "like_count": cm["likes"],
                        "user_region": cm["nick"],
                        "source_url": f"https://music.163.com/#/song?id={song['id']}",
                        "collected_at": date.today().isoformat(),
                    })
                total += len(comments)
                handle.flush()
                time.sleep(1.2)
            print(f"  {artist}: {len(songs)} 首歌, 共 {total} 当前累计", flush=True)
    print(f"done. total comments: {total}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--artists-file", default=None, help="艺人名单文件(每行一个), 不传则自动从采集CSV收集")
    parser.add_argument("--out", default="data/raw/comments_wyy.csv", help="输出CSV路径")
    parser.add_argument("--songs", type=int, default=4, help="每个艺人的歌曲数")
    parser.add_argument("--pages", type=int, default=3, help="每首歌热评页数(每页15条)")
    parser.add_argument("--limit", type=int, default=None, help="艺人数量上限(调试用)")
    args = parser.parse_args()

    if args.artists_file:
        with open(args.artists_file, encoding="utf-8") as fh:
            artists = [line.strip() for line in fh if line.strip()]
        print(f"艺人名单(文件): {len(artists)} 位", flush=True)
    else:
        artists = _load_artists(limit=args.limit)
        print(f"艺人名单(自动收集,去重后): {len(artists)} 位, 开始采集", flush=True)
    collect(artists, max_songs=args.songs, per_song=args.pages, out_path=args.out)
