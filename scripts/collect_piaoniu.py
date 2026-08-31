#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
票牛网（piaoniu.com）演唱会/演出全量采集脚本
================================================================
数据源 : https://www.piaoniu.com/sh-all?page=N （静态渲染演出列表）
  - 列表页: /sh-all?page=N 每页 10 个巡演聚合(stag)
  - 聚合页: /stag/{id} 列出该演出所有城市的独立场次(activity)
  - 场次页: /activity/{id} 含时间/场馆/票价/状态
采集策略:
  - 低频采集: 列表页/聚合页间隔 >= 3 秒
  - UA 模拟普通浏览器, 请求失败重试 2 次
  - 不绕过验证码/反爬, 仅采集公开静态页面
输出   : data/raw/piaoniu_concerts.csv (UTF-8 with BOM)
列     : artist_name, concert_name, city, venue, show_time, price_text,
         sale_status, source_type, source_url, collected_at
"""

import argparse
import csv
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.piaoniu.com"
LIST_URL = BASE_URL + "/sh-all?page={page}"
STAG_URL = BASE_URL + "/stag/{sid}"
ACTIVITY_URL = BASE_URL + "/activity/{aid}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 只采集演唱会/音乐现场类（标题命中任一关键字）
INCLUDE_KEYWORDS = (
    "演唱会", "音乐会", "巡演", "现场", "Live", "live", "音乐节",
    "专场", "演出", "巡", "tour", "电音节", "音乐秀", "音乐史诗",
    "巡唱", "巡回", "摇滚", "爵士", "金属", "后朋", "乐队", "视听交响",
)
EXCLUDE_KEYWORDS = (
    "话剧", "喜剧", "脱口秀", "展览", "舞台剧", "音乐剧", "折子戏",
    "儿童剧", "亲子", "放映", "魔术秀", "年票", "景区", "大赛", "运动会",
    "体育", "博览会", "市集", "书展", "漫展", "剧本杀", "密室", "露营",
    "讲座", "见面会", "沙龙", "昆曲", "黄梅", "京剧", "豫剧", "越剧",
    "沪剧", "评剧", "川剧", "粤剧", "舞剧", "木偶", "皮影", "杂技",
    "曲艺", "评弹", "舞蹈", "相声", "二人转",
    "单口", "脱口秀专场", "喜剧专场", "互动", "巡游", "烟花秀",
    "灯光秀", "无人机秀", "体育", "足球", "篮球",
)

FIELDNAMES = [
    "artist_name", "concert_name", "city", "venue", "show_time",
    "price_text", "sale_status", "source_type", "source_url", "collected_at",
]


def _normalize(text):
    if not text:
        return ""
    text = text.replace("\u00a0", " ").replace("&middot;", "·")
    text = text.replace("&ldquo;", """""").replace("&rdquo;", """""").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def _fetch(url, retries=2):
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException:
            pass
        time.sleep(2 + attempt * 2)
    return None


def _artist_from_title(title):
    """从 '[北京]王俊凯演唱会北京站' 提取艺人名（返回空串则上层用默认值）"""
    t = title
    # 1) 删城市前缀
    t = re.sub(r"^\[[^\]]+\]", "", t)
    # 2) 删 [代拍费]/[预定金]/[限时立减] 及类似前缀
    t = re.sub(r"^\s*[\[【（(]?(代拍费|预定金|代拍|定金|限时立减\d*\.?\d*元)[\]】）)]?\s*", "", t)
    t = re.sub(r"&times;|×", "/", t)
    # 3) 切第一个“演唱会/巡演/音乐会/音乐节/专场”之前的部分
    cut = re.split(r"(演唱会|巡回演唱会|巡演|音乐会|音乐节|专场|巡唱|LIVE|Live)", t, maxsplit=1)
    t = cut[0]
    # 4) 删年份与书名号/引号装饰
    t = re.sub(r"20\d\d", " ", t)
    t = re.sub(r"「.*?」|“.*?”|《.*?》|‘.*?’", " ", t)
    # 5) 删多余空格与首尾杂符号
    t = re.sub(r"\s+", " ", t).strip(" .·-&|/、：:！!？?（）()")
    if not t:
        return ""
    # 5a) 【装饰】开头视为无艺人
    if t.startswith("【"):
        return ""
    # 5b) 保留 [艺人A/艺人B] 这种多艺人块（去括号），否则视为无艺人
    if t.startswith("[") and "]" in t:
        inner = t[1:t.index("]")]
        if "/" in inner or "、" in inner:
            return inner.strip()[:40]
        return ""
    # 6) 纯英文/品牌名（无中文人名特征）视为无艺人
    if not re.search(r"[一-龥]", t):
        return ""
    return t[:40].strip() if t else ""

def _parse_stag(sid, html):
    """从聚合页解析所有城市场次 activity"""
    items = []
    for m in re.finditer(
        r'class="title"><a href="//www\.piaoniu\.com/activity/(\d+)"[^>]*title="([^"]+)"',
        html,
    ):
        aid, title = m.group(1), m.group(2)
        items.append({"aid": aid, "title": _normalize(title)})
    return items


def _fetch_activity(aid, title):
    html = _fetch(ACTIVITY_URL.format(aid=aid))
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    # concert_name: data-id 区块标题（可能含城市前缀）
    name = _normalize(title)
    city = ""
    cm = re.match(r"^\[([^\]]+)\]", title)
    if cm:
        city = _normalize(cm.group(1))
    cm2 = re.search(r'class="desc">([^<]+)</div>', html)
    show_time = ""
    if cm2:
        show_time = _normalize(cm2.group(1)).split("  ")[0]
        if len(show_time.split(" ")) >= 2:
            show_time = show_time.split(" ")[0] + " " + show_time.split(" ")[1]
    venue = ""
    vm = re.search(r'class="desc">([^<]+)</div>', html)
    if vm:
        parts = _normalize(vm.group(1)).split(" ")
        # desc: "2026.10.25 19:30 场馆名" 或 "10.06 - 国家体育场" 等
        if len(parts) >= 3:
            venue_parts = parts[2:]
            # 若场馆片段带 "10.07"/"12.31" 等日期词则去掉
            venue_parts = [p for p in venue_parts if not re.match(r"^\d{1,2}\.\d{1,2}$", p)]
            venue = " ".join(venue_parts)
    price_text = ""
    pm = re.search(r'class="sale-price">\s*&#x00a5;\s*<span class="strong">(\d+)</span>', html)
    if pm:
        price_text = pm.group(1) + " 起"
    status = "待定"
    for s, v in (("booking", "预售中"), ("sale", "售票中"), ("sold", "已售罄"), ("end", "已结束")):
        if f'class="status {s}"' in html or f'class="eticket status {s}"' in html:
            status = v
            break
    artist = _artist_from_title(name)
    return {
        "artist_name": artist,
        "concert_name": name,
        "city": city,
        "venue": venue,
        "show_time": show_time,
        "price_text": price_text,
        "sale_status": status,
        "source_type": "爬虫采集",
        "source_url": ACTIVITY_URL.format(aid=aid),
        "collected_at": date.today().isoformat(),
    }


def collect_list(max_pages=200, resume=True):
    out = Path("data/raw/piaoniu_concerts.csv")
    fieldnames = ["stag_id", "activity_id", "title"]
    seen = set()
    rows = []

    # 断点续采：已有 CSV 去掉头部读取已采集的 activity_id
    collected = set()
    if resume and out.exists():
        with out.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                collected.add(row.get("source_url", "").split("/")[-1])

    log = Path("data/raw/piaoniu_collect.log")
    with out.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        if not out.exists() or out.stat().st_size == 0:
            writer.writeheader()

        for page in range(1, max_pages + 1):
            html = _fetch(LIST_URL.format(page=page))
            if not html:
                print(f"page{page}: fetch failed, retry later")
                log.write_text(f"{date.today()} page{page}: fetch failed\n", encoding="utf-8")
                continue
            stags = set(re.findall(r'href="//www\.piaoniu\.com/stag/(\d+)"', html))
            for sid in stags:
                stag_html = _fetch(STAG_URL.format(sid=sid))
                if not stag_html:
                    continue
                activities = _parse_stag(sid, stag_html)
                print(f"  stag {sid}: {len(activities)} activities")
                for act in activities:
                    if act["aid"] in collected:
                        continue
                    rec = _fetch_activity(act["aid"], act["title"])
                    if rec and rec.get("concert_name"):
                        writer.writerow(rec)
                        handle.flush()
                        collected.add(act["aid"])
                time.sleep(3)
            if not stags:
                print(f"page{page}: empty, stop")
                break
            print(f"page{page}: {len(stags)} stags")
            time.sleep(3)
    print(f"done. total activities: {len(collected)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    collect_list(max_pages=args.max_pages, resume=not args.no_resume)
