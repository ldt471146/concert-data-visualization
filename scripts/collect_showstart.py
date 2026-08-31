#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
秀动网（showstart.com）演唱会 / 音乐现场演出数据采集脚本
================================================================
数据源 : https://www.showstart.com/event/list?type=1&pageNo=N （公开静态渲染列表页）
采集策略:
  - 低频采集: 列表页间隔 >= 3 秒, 详情页间隔 >= 2 秒
  - UA 模拟普通浏览器 (Mozilla/5.0 ...)
  - 请求失败重试 2 次 (共 3 次尝试), 仍失败则跳过并记录
  - 不绕过任何验证码 / 反爬机制, 仅采集公开页面
输出   : data/raw/showstart_concerts.csv (UTF-8 with BOM)
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

BASE_URL = "https://www.showstart.com"
LIST_URL = BASE_URL + "/event/list?type=1&pageNo={page}"
EVENT_URL = BASE_URL + "/event/{eid}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 只采集演唱会 / 音乐现场类演出（命中任一关键字）
INCLUDE_KEYWORDS = (
    # 标题命中任一即视为演唱会 / 音乐现场类
    "演唱会", "音乐会", "巡演", "现场", "Live", "live", "音乐节",
    # 秀动现场音乐标题常用词（专场/演出/TOUR/巡 XX 站/电音节/摇滚/爵士等）
    "专场", "演出", "巡", "tour", "电音节", "音乐秀", "音乐史诗",
    "巡唱", "巡回", "摇滚", "爵士", "金属", "后朋", "乐队",
)
# 跳过话剧 / 喜剧 / 展览 及明显非现场音乐类目
EXCLUDE_KEYWORDS = (
    "话剧", "喜剧", "脱口秀", "展览", "舞台剧", "音乐剧", "折子戏", "戏曲",
    "儿童剧", "亲子", "高清放映", "放映", "科学秀", "魔术秀", "年票", "景区",
    "大赛", "运动会", "体育", "博览会", "市集", "书展", "漫展", "剧本杀",
    "密室", "露营", "讲座", "见面会", "沙龙",
    # 传统戏曲 / 舞蹈类（避免“专场”等词误收录）
    "昆曲", "黄梅", "京剧", "豫剧", "越剧", "沪剧", "评剧", "川剧", "粤剧",
    "舞剧", "木偶", "皮影", "杂技", "曲艺", "评弹",
)

FIELDNAMES = [
    "artist_name", "concert_name", "city", "venue", "show_time",
    "price_text", "sale_status", "source_type", "source_url", "collected_at",
]

NUM_CN_RE = re.compile(r"[\u4e00-\u9fff]")


def log(msg):
    print(msg, flush=True)


def http_get(url, retries=2, timeout=20):
    """GET 请求, 失败重试 retries 次; 返回 Response 或 None。"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp
            last_err = "HTTP %s" % resp.status_code
            if resp.status_code == 429:  # 被限流, 多等一会
                time.sleep(8)
        except requests.RequestException as exc:
            last_err = "%s: %s" % (type(exc).__name__, exc)
        if attempt < retries:
            time.sleep(3)
    return None


def in_scope(title):
    """是否属于演唱会 / 音乐现场类（含 Live）；排除话剧/喜剧/展览等。"""
    if not title:
        return False
    lowered = title.lower()
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return False
    return any(k in lowered for k in INCLUDE_KEYWORDS)


def norm_list_anchor(text):
    """解析列表页事件链接文本, 返回字段 dict 或 None。

    锚文本格式: {标题} 艺人：{艺人} 价格：{价格} 时间：{yyyy/mm/dd hh:mm} [{城市}]{场馆}
    """
    text = re.sub(r"\s+", " ", text).strip()
    pat = re.compile(
        r"^(?P<title>.+?)\s*艺人：\s*(?P<artist>[^价]*?)\s*价格：\s*"
        r"(?P<price>.*?)\s*时间：\s*(?P<date>\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2})"
        r"(?:\s*\[(?P<city>[^\]]*)\](?P<venue>.*?))?\s*$"
    )
    m = pat.match(text)
    if not m:
        # 兼容个别不带字段标签的链接：整段视为标题
        return {"title": text, "artist": "", "price": "", "date": "",
                "city": "", "venue": ""}
    artist = (m.group("artist") or "").strip()
    if artist in ("待定", "暂无", "无"):
        artist = ""
    return {
        "title": (m.group("title") or "").strip(),
        "artist": artist,
        "price": (m.group("price") or "").strip(),
        "date": (m.group("date") or "").strip(),
        "city": (m.group("city") or "").strip(),
        "venue": (m.group("venue") or "").strip(),
    }


def fetch_list_page(page, session):
    """抓取一页列表, 返回 [(eid, info), ...]（链接去重）。"""
    url = LIST_URL.format(page=page)
    resp = http_get(url)
    if resp is None:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    out = []
    seen = set()
    for a in soup.find_all("a", href=re.compile(r"/event/\d+")):
        m = re.search(r"/event/(\d+)", a.get("href") or "")
        if not m:
            continue
        eid = m.group(1)
        if eid in seen:
            continue
        info = norm_list_anchor(a.get_text(" ", strip=True))
        if not info["title"]:
            continue
        seen.add(eid)
        out.append((eid, info))
    return out


def parse_detail(html):
    """解析详情页, 返回 dict(oslides) 或 None。"""
    soup = BeautifulSoup(html, "html.parser")
    desc = soup.find("div", class_="describe")
    if desc is None:
        return None
    title_el = desc.find("div", class_="title")
    title = title_el.get_text(" ", strip=True) if title_el else ""

    d_time = d_artist = d_venue = ""
    for p in desc.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if txt.startswith("演出时间："):
            d_time = txt[len("演出时间："):].strip()
        elif txt.startswith("艺人："):
            d_artist = txt[len("艺人："):].strip()
        elif txt.startswith("场地："):
            d_venue = txt[len("场地："):].strip()

    city = venue = ""
    if d_venue:
        parts = d_venue.split(" ", 1)
        city = parts[0].strip()
        venue = parts[1].strip() if len(parts) > 1 else ""

    prices = []
    buy = soup.find("div", class_="buy")
    if buy is not None:
        for span in buy.select(".price-tags span"):
            m = re.search(r"￥\s*([\d.]+)", span.get_text())
            if m:
                prices.append(m.group(1))
    price_text = " / ".join(dict.fromkeys(prices)) or "待定"

    return {
        "title": title,
        "time_raw": d_time,
        "artist": d_artist,
        "city": city,
        "venue": venue,
        "price": price_text,
        "has_price_block": bool(prices),
    }


def norm_date(s):
    """把 2026/07/26 19:30 或 2026年7月26日 19:30 规范为 2026-07-26 19:30。"""
    if not s:
        return ""
    m = re.search(
        r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})(?:\s*[日号])?"
        r"(?:\s+(\d{1,2}):(\d{2}))?",
        s,
    )
    if not m:
        return s.strip()
    base = "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    if m.group(4):
        base += " %s:%s" % (m.group(4), m.group(5))
    return base


def artist_from_title(title):
    """保守地从标题抽取艺人名（仅当存在显式分隔符 "-- / -" 且后接短名称 + 年份/关键词）。

    例如: 《我只在乎你》--陈佳 2026 邓丽君经典金曲专场演唱会 -> 陈佳
    无法可靠抽取时返回 ""（不臆造）。
    """
    if not title:
        return ""
    m = re.search(
        r"[《«\u201c\"']?[^》»\u201d\"]*?[》»\u201d\"]?\s*[-—－–]\s*"
        r"([\u4e00-\u9fff·]{1,8}[\u4e00-\u9fff·]?)"
        r"(?=\s*(?:\d{4}\s*年?|\d{1,2}\s*月|演唱会|专场|巡回|巡演|音乐会|Live))",
        title,
    )
    if not m:
        return ""
    name = m.group(1).strip("· ")
    if not NUM_CN_RE.search(name):
        return ""
    return name


def main():
    parser = argparse.ArgumentParser(description="秀动网演唱会/音乐现场数据采集")
    parser.add_argument("--max-pages", type=int, default=30, help="列表页上限（默认 30）")
    parser.add_argument("--list-delay", type=float, default=3.0, help="列表页请求间隔秒（默认 3）")
    parser.add_argument("--detail-delay", type=float, default=2.0, help="详情页请求间隔秒（默认 2）")
    parser.add_argument("--start-page", type=int, default=1, help="从第几页开始抓列表")
    parser.add_argument("--output", default="data/raw/showstart_concerts.csv")
    parser.add_argument("--log", default="data/raw/showstart_collect.log")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log)
    today = date.today().isoformat()

    failures = []
    session = requests.Session()
    session.headers.update(HEADERS)

    # ---------------- 第一步：列表页采集 ----------------
    events = {}  # eid -> list info
    page = args.start_page
    while page <= args.max_pages:
        items = fetch_list_page(page, session)
        if items is None:
            failures.append({"stage": "list", "page": page,
                             "reason": "请求失败（重试后仍失败）"})
            log("[列表] 第 %d 页 请求失败，跳过" % page)
            time.sleep(args.list_delay)
            page += 1
            continue
        new_ids = [eid for eid, info in items if eid not in events]
        for eid, info in items:
            if eid not in events:
                events[eid] = info
        total = len(events)
        log("[列表] 第 %d 页：%d 条链接, 新增 %d 条, 累计唯一 %d 条"
            % (page, len(items), len(new_ids), total))
        if not new_ids:  # API 不再返回新 event，停止翻页
            log("[列表] 第 %d 页无新 event，停止翻页" % page)
            break
        time.sleep(args.list_delay)
        page += 1

    in_scope_events = {eid: info for eid, info in events.items()
                       if in_scope(info["title"])}
    skipped = [eid for eid, info in events.items() if eid not in in_scope_events]
    log("=" * 60)
    log("[过滤] 列表共 %d 个唯一 event，命中演唱会/音乐现场类 %d 个，跳过 %d 个（话剧/喜剧/展览等）"
        % (len(events), len(in_scope_events), len(skipped)))

    # ---------------- 第二步：详情页采集 ----------------
    # 断点续跑：跳过已在 CSV 中的 event
    existing_ids = set()
    if out_path.exists():
        with out_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                m = re.search(r"/event/(\d+)", row.get("source_url", ""))
                if m:
                    existing_ids.add(m.group(1))
    todo = [eid for eid in in_scope_events if eid not in existing_ids]
    has_header = out_path.exists() and out_path.stat().st_size > 0
    fh = out_path.open("a" if has_header else "w",
                       encoding="utf-8-sig", newline="")
    writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
    if not has_header:
        writer.writeheader()
        fh.flush()

    rows_written = 0
    fail_detail = []
    n = len(todo)
    for i, eid in enumerate(todo, 1):
        url = EVENT_URL.format(eid=eid)
        resp = http_get(url)
        if resp is None:
            fail_detail.append({"url": url, "reason": "详情页请求失败（重试后仍失败）"})
            log("[详情] %d/%d event=%s 请求失败，跳过" % (i, n, eid))
        else:
            detail = parse_detail(resp.text)
            if detail is None or not detail["title"]:
                reason = "解析失败（未找到演出标题）"
                if detail is None:
                    reason = "解析失败（页面结构异常）"
                fail_detail.append({"url": url, "reason": reason})
                log("[详情] %d/%d event=%s %s，使用列表页数据降级" % (i, n, eid, reason))
            else:
                reason = None

            info = in_scope_events[eid]
            d = detail or {}
            # ---- 组装字段 ----
            title = d.get("title") or info["title"]
            detail_time = d.get("time_raw", "")
            show_time = norm_date(detail_time)
            if not show_time or "年" not in show_time and not re.search(r"\d{4}", show_time):
                # 详情页无年份时退回列表页自带完整日期（时间字段）
                show_time = norm_date(info["date"]) or show_time or "待定"
            if not show_time:
                show_time = detail_time or "待定"

            artist = d.get("artist") or info["artist"] or artist_from_title(title)
            artist = artist.strip()
            if artist in ("待定", "暂无", "无"):
                artist = ""

            city = d.get("city") or info["city"]
            venue = d.get("venue") or info["venue"]
            price_text = "待定" if not info["price"] or info["price"] == "待定" \
                else info["price"]
            if d.get("has_price_block"):
                price_text = d["price"]

            row = {
                "artist_name": artist,
                "concert_name": title,
                "city": city,
                "venue": venue,
                "show_time": show_time,
                "price_text": price_text,
                "sale_status": "待定",
                "source_type": "爬虫采集",
                "source_url": url,
                "collected_at": today,
            }
            writer.writerow(row)
            rows_written += 1
            if i % 10 == 0 or i == n:
                log("[详情] 进度 %d/%d，累计写入 %d 行" % (i, n, rows_written))
        fh.flush()
        if i < n:
            time.sleep(args.detail_delay)

    fh.close()

    # ---------------- 收尾 ----------------
    all_failures = failures + fail_detail
    with log_path.open("w", encoding="utf-8") as lf:
        lf.write("秀动网采集日志 %s\n" % today)
        lf.write("列表唯一 event: %d, 演唱会类: %d\n" % (len(events), len(in_scope_events)))
        lf.write("详情请求数: %d, 成功写入: %d, 失败/跳过: %d\n"
                 % (len(todo), rows_written, len(all_failures)))
        for f in all_failures:
            lf.write("%s\n" % f)
    for f in all_failures:
        log("[失败记录] %s" % f)
    log("=" * 60)
    log("完成：CSV 输出 %s，共 %d 行（含续跑时已存在的行则更多）"
        % (out_path, rows_written))
    return 0


if __name__ == "__main__":
    sys.exit(main())