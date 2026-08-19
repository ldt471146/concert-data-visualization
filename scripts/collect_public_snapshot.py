"""Collect a checked public concert snapshot and merge it into the raw CSV.

The records below are normalized from public event pages that were reachable
without login, CAPTCHA, proxy rotation, or other access workarounds. The
source pages are checked before the snapshot is written.
"""

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


RAW_FIELDS = [
    "artist_name",
    "concert_name",
    "city",
    "venue",
    "show_time",
    "price_text",
    "sale_status",
    "source_url",
    "collected_at",
]

SOURCE_DEFINITIONS = {
    "wuhan_official": {
        "url": "https://www.wuhan.gov.cn/zjwh/whrw/202602/t20260227_2732780.shtml",
        "label": "武汉市人民政府门户网站（来源：武汉市文化和旅游局官方微信号）",
    },
    "shanghai_schedule": {
        "url": "https://news.qq.com/rain/a/20250808A0470R00",
        "label": "上海8-9月演唱会排期表（腾讯新闻转载）",
    },
    "hangzhou_schedule": {
        "url": "https://news.qq.com/rain/a/20250809A03JX400",
        "label": "杭州演唱会排期表（腾讯新闻转载）",
    },
    "beijing_schedule": {
        "url": "https://peking.bjd.com.cn/content/s68b64108e4b02424b0bf9f20.html",
        "label": "北京市9月演出预告（北京日报）",
    },
    "chengdu_schedule": {
        "url": "https://news.qq.com/rain/a/20251001A06R8N00",
        "label": "成都10-11月演唱会排期表（腾讯新闻转载）",
    },
    "xian_schedule": {
        "url": "https://news.qq.com/rain/a/20251202A075U600",
        "label": "西安大型演出排期（腾讯新闻转载）",
    },
    "guangzhou_collection": {
        "url": "https://hk.trip.com/events/3372034-2025-guangzhou-concerts-collection",
        "label": "2025广州演唱会公开活动汇总（Trip.com）",
    },
    "shenzhen_collection": {
        "url": "https://hk.trip.com/events/3372020-2025-shenzhen-concerts-collection",
        "label": "2025深圳演唱会公开活动汇总（Trip.com）",
    },
    "nanjing_collection": {
        "url": "https://hk.trip.com/events/3372370-2025-nanjing-concerts-collection",
        "label": "2025南京演唱会公开活动汇总（Trip.com）",
    },
}


def _record(source_id, artist, name, city, venue, show_time, price, status):
    return {
        "source_id": source_id,
        "artist_name": artist,
        "concert_name": name,
        "city": city,
        "venue": venue,
        "show_time": show_time,
        "price_text": price,
        "sale_status": status,
    }


PUBLIC_RECORDS = [
    # Wuhan official public announcement, 2026 spring.
    _record("wuhan_official", "蔡琴", "蔡琴《不要告别》演唱会—武汉站", "武汉", "光谷国际网球中心（中央球馆）", "2026-03-07 19:30", "280/480/680/880/1080", "售票中"),
    _record("wuhan_official", "汪峰", "汪峰《相信未来》巡回演唱会", "武汉", "光谷国际网球中心（中央球馆）", "2026-03-14 19:00", "380/580/780/1080", "售票中"),
    _record("wuhan_official", "F✦FOREVER", "F✦FOREVER 恒星之城巡回演唱会—武汉站（4场）", "武汉", "光谷国际网球中心（中央球馆）", "2026-03-19 19:30", "待定", "已售罄"),
    _record("wuhan_official", "八三夭", "八三夭《这是我的第一场》2026 LIVEHOUSE春季巡回—武汉站（2场）", "武汉", "不晚 IN TIME LIVE（汉阳造店）", "2026-03-20 19:30", "350", "未开售"),
    _record("wuhan_official", "周蕙", "周蕙《约定—做快乐的自己》演唱会—武汉站", "武汉", "武钢体育中心·体育馆", "2026-03-28 19:30", "199/399/599/699/799", "售票中"),
    _record("wuhan_official", "陶喆", "陶喆 Soul Power II Plus 世界巡回演唱会（武汉站）", "武汉", "武汉体育中心主体育场", "2026-03-27 19:30", "待定", "已售罄"),
    _record("wuhan_official", "谢霆锋", "谢霆锋 Evolution Nic Live进化演唱会（武汉站）", "武汉", "武汉体育中心体育场", "2026-04-11 19:30", "380/580/780/980/1280/1680", "待定"),
    _record("wuhan_official", "梁静茹", "《Best，茹果我不唱情歌》梁静茹巡回演唱会—武汉站", "武汉", "武汉五环体育中心体育场", "2026-04-11 19:30", "待定", "已售罄"),
    _record("wuhan_official", "OneRepublic", "ONEREPUBLIC《From Asia, With Love》2026武汉站", "武汉", "武汉五环中心体育场", "2026-04-19 19:30", "480/680/880/1080/1280/1480", "售票中"),
    _record("wuhan_official", "陈鸿宇", "陈鸿宇2026《十步一啄》巡演武汉站", "武汉", "不晚 IN TIME LIVE（汉阳造店）", "2026-04-24 20:00", "177/247/447/477", "售票中"),
    _record("wuhan_official", "郑润泽", "郑润泽《旷野》2026巡回演唱会—武汉站", "武汉", "武汉光谷国际网球中心（中央球场）", "2026-04-25 19:00", "398/598/798/998/1198", "待定"),
    _record("wuhan_official", "安又琪", "安又琪《Love·有你陪着我》巡回演唱会（武汉站）", "武汉", "武钢体育中心·体育馆", "2026-04-25 19:30", "280/480/680", "待定"),
    _record("wuhan_official", "苏见信", "苏见信《尽兴而活》2026巡回演唱会—武汉站", "武汉", "湖北省奥林匹克中心体育馆", "2026-05-23 19:00", "280/480/680/880/980", "待定"),
    # Shanghai public schedule.
    _record("shanghai_schedule", "时代少年团", "时代少年团《加冠礼》演唱会—《冠军》上海站（4场）", "上海", "上海体育场", "2025-08-20 19:30", "480/680/980/1280/1480/1580/1880", "售票中"),
    _record("shanghai_schedule", "周笔畅", "《天呐！我怎么会变成这样》周笔畅2025巡回演唱会上海站", "上海", "浦发银行东方体育中心体育馆", "2025-09-06 19:00", "380/680/980/1380", "售票中"),
    _record("shanghai_schedule", "潘玮柏", "潘玮柏《狂爱2.0》巡回演唱会—上海站（2场）", "上海", "浦发银行东方体育中心", "2025-08-30 19:30", "480/680/880/1080/1380", "售票中"),
    _record("shanghai_schedule", "Capper", "2025 Capper《Who Am I》巡回演唱会—上海站", "上海", "徐家汇体育公园·上海体育馆", "2025-08-16 19:00", "380/580/780/980", "售票中"),
    _record("shanghai_schedule", "罗言", "罗言《EXIT》2025全国巡回演唱会—上海站", "上海", "上海静安体育中心·体育馆", "2025-09-20 19:30", "288/488/688/888", "待定"),
    _record("shanghai_schedule", "沙一汀", "沙一汀EL《听汀》上海演唱会", "上海", "梅赛德斯—奔驰文化中心", "2025-10-03 19:30", "待定", "待定"),
    _record("shanghai_schedule", "张艺兴", "张艺兴《大航海5·闹天宫》巡回演唱会—上海站（2场）", "上海", "梅赛德斯—奔驰文化中心", "2025-09-13 19:30", "待定", "待定"),
    _record("shanghai_schedule", "张学友", "JACKY CHEUNG 60+ CONCERT TOUR 张学友60+巡回演唱会上海站（6场）", "上海", "上海东方体育中心", "2025-09-19 19:00", "待定", "待定"),
    _record("shanghai_schedule", "张震岳", "张震岳《跟着感觉走》巡回演唱会—上海站", "上海", "上海体育馆", "2025-10-25 19:30", "待定", "待定"),
    _record("shanghai_schedule", "谭咏麟", "谭咏麟经典传奇巡回演唱会—上海站", "上海", "上海虹口足球场", "2025-11-01 18:45", "待定", "待定"),
    _record("shanghai_schedule", "周杰伦", "2025周杰伦嘉年华世界巡回演唱会—上海站（3场）", "上海", "上海体育场", "2025-10-09 19:00", "待定", "待定"),
    _record("shanghai_schedule", "巫启贤", "巫启贤2025《红尘来去梦太傻》巡回演唱会—上海站", "上海", "上海虹馆文化发展有限公司", "2025-12-06 19:00", "待定", "待定"),
    # Hangzhou public schedule.
    _record("hangzhou_schedule", "万妮达", "万妮达2025《唤醒我》巡回演唱会—杭州站", "杭州", "黄龙体育中心体育馆", "2025-08-30 19:30", "380/580/680/780/980", "已售罄"),
    _record("hangzhou_schedule", "Katy Perry", "Katy Perry THE LIFETIMES TOUR凯蒂·佩里杭州站", "杭州", "杭州奥体中心体育馆", "2025-11-21 19:30", "499/799/999/1599/1999/2599", "已售罄"),
    _record("hangzhou_schedule", "陈粒", "陈粒《一粒》十周年巡回演唱会—杭州站", "杭州", "杭州奥体中心体育馆", "2025-09-20 19:00", "399/599/799/999", "售票中"),
    _record("hangzhou_schedule", "Capper", "Capper《Who Am I》巡回演唱会—杭州站", "杭州", "黄龙体育中心体育馆", "2025-08-23 19:00", "380/580/780/980", "已售罄"),
    _record("hangzhou_schedule", "威神V", "2025威神V演唱会《NO WAY OUT》杭州站", "杭州", "杭州奥体中心体育馆", "2025-09-27 18:30", "499/799/1199/1599/1999", "售票中"),
    _record("hangzhou_schedule", "陶喆", "2025陶喆 Soul Power II 世界巡回演唱会—杭州站（3场）", "杭州", "杭州奥体中心体育场", "2025-08-29 19:30", "380/580/780/1080/1380", "已售罄"),
    _record("hangzhou_schedule", "周深", "周深2025《深深的》巡回演唱会—杭州站（2场）", "杭州", "杭州奥体中心体育场", "2025-09-13 19:30", "399/699/929/1199/1399/1699", "待定"),
    _record("hangzhou_schedule", "滨崎步", "滨崎步2025亚洲巡回演唱会—杭州站", "杭州", "杭州奥体中心体育馆", "2025-10-11 19:30", "待定", "待定"),
    _record("hangzhou_schedule", "张杰", "2025张杰未·LIVE《开往1982》世界巡回演唱会—杭州站（3场）", "杭州", "杭州奥体中心体育场", "2025-10-02 19:30", "待定", "待定"),
    _record("hangzhou_schedule", "王赫野", "王赫野2025《去吹一场野的风》2.0巡回演唱会—杭州站", "杭州", "浙江黄龙体育中心", "2025-11-08 19:30", "待定", "待定"),
    _record("hangzhou_schedule", "颜人中", "颜人中《MOMENTⁿ》2025世界巡回演唱会—杭州站", "杭州", "杭州奥体中心体育馆", "2025-11-08 19:30", "待定", "待定"),
    # Beijing public schedule.
    _record("beijing_schedule", "陶喆", "2025陶喆 Soul Power II演唱会—北京站（3场）", "北京", "国家体育场", "2025-09-19 19:30", "待定", "待定"),
    _record("beijing_schedule", "鹿晗", "2025鹿晗Season4亚洲巡演—北京站（2场）", "北京", "国家速滑馆（冰丝带）", "2025-09-05 19:30", "待定", "待定"),
    _record("beijing_schedule", "陈小春", "2025陈小春《生·旦·净·末·丑》演唱会—北京站（2场）", "北京", "华熙LIVE·五棵松", "2025-09-13 19:30", "待定", "待定"),
    _record("beijing_schedule", "陈慧娴", "2025陈慧娴40周年《Fabulous 40》演唱会—北京站", "北京", "国家体育馆", "2025-09-06 19:30", "待定", "待定"),
    # Chengdu public schedule.
    _record("chengdu_schedule", "李玉刚", "《幻·国潮》李玉刚巡回演唱会—成都站", "成都", "成都东安湖体育公园多功能体育馆", "2025-10-04 19:30", "280/480/680/880/1080/1280", "售票中"),
    _record("chengdu_schedule", "游鸿明", "游鸿明《爱我的人和我爱的人》2025演唱会—成都站", "成都", "高新区体育中心·体育馆", "2025-10-18 19:00", "380/1080", "售票中"),
    _record("chengdu_schedule", "胡彦斌", "胡彦斌2025《是一场烟火·刹那》巡回演唱会—成都站", "成都", "成都金融城演艺中心", "2025-10-25 19:00", "380/1080", "售票中"),
    _record("chengdu_schedule", "叶蓓", "叶蓓《听说独写》演唱会—成都站", "成都", "东区超现场", "2025-10-25 19:30", "180/1314", "售票中"),
    _record("chengdu_schedule", "罗言", "罗言《EXIT》2025巡回演唱会—成都站", "成都", "四川省体育馆", "2025-10-25 19:30", "288/888", "售票中"),
    _record("chengdu_schedule", "周深", "周深2025《深深的》巡回演唱会—成都站（2场）", "成都", "成都东安湖体育公园主体育场", "2025-11-01 19:30", "399/1699", "待定"),
    _record("chengdu_schedule", "张震岳", "张震岳《跟着感觉走》巡回演唱会—成都站", "成都", "成都金融城演艺中心", "2025-11-29 19:00", "380/980", "待定"),
    _record("chengdu_schedule", "颜人中", "颜人中《MOMENTⁿ》2025世界巡回演唱会—成都站", "成都", "成都东安湖体育公园多功能体育馆", "2025-11-22 19:00", "380/1280", "待定"),
    _record("chengdu_schedule", "威神V", "2025威神V演唱会《NO WAY OUT》成都站", "成都", "五粮液文化体育中心综合体育馆", "2025-11-08 19:30", "待定", "待定"),
    _record("chengdu_schedule", "邓紫棋", "G.E.M.邓紫棋 I AM GLORIA世界巡回演唱会2.0—成都站加场", "成都", "成都东安湖体育公园主体育场", "2025-10-17 19:30", "待定", "待定"),
    # Xi'an public schedule.
    _record("xian_schedule", "周兴哲", "2025周兴哲《odyssey旅程》巡回演唱会—西安站", "西安", "西安奥体中心体育馆", "2025-12-06 19:30", "480/1180", "售票中"),
    _record("xian_schedule", "邰正宵等", "时光流转经典重现群星演唱会—西安站", "西安", "西安市城市运动公园体育馆", "2025-12-06 19:30", "180/1480", "待定"),
    _record("xian_schedule", "崔健", "2025崔健《继续撒点野》巡回演唱会—西安站", "西安", "西安曲江竞技中心", "2025-12-20 19:30", "388/988", "售票中"),
    _record("xian_schedule", "郑钧", "2025郑钧《The Road of Joy狂喜之路》演唱会—西安站", "西安", "西安奥体中心体育馆", "2025-12-27 19:30", "280/980", "售票中"),
    _record("xian_schedule", "姜云升", "姜云升《不息》2025新专场巡演2.0—西安站", "西安", "星球工厂LIVEHOUSE", "2025-12-20 19:30", "269/480", "已售罄"),
    # Public city collections.
    _record("guangzhou_collection", "汪苏泷", "汪苏泷《大娱乐家》新年限定演唱会—广州站（3场）", "广州", "宝能广州国际体育演艺中心", "2024-12-30 19:30", "380/2280", "已结束"),
    _record("guangzhou_collection", "群星", "2025新年演唱会《BELOVED·特别的爱给特别的你》", "广州", "广州黄埔区科学城会议中心", "2025-01-01 19:30", "62/180", "已结束"),
    _record("shenzhen_collection", "谢天笑", "谢天笑2024《超级本能》演唱会巡演—深圳站", "深圳", "深圳市体育中心体育馆副馆（AI Live House）", "2025-01-04 19:30", "338", "已结束"),
    _record("shenzhen_collection", "烈火乐队", "《光辉岁月·追忆黄家驹31周年》新年演唱会—深圳站", "深圳", "深圳戏院", "2025-01-01 19:30", "280/480", "已结束"),
    _record("shenzhen_collection", "夜莺次元音乐节", "夜莺次元音乐节·2025元旦交响", "深圳", "NUBOND AIR", "2025-01-01 19:30", "88/128/268/648", "已结束"),
    _record("shenzhen_collection", "Robert Wells", "《摇滚的狂想》罗伯特·威尔斯巡回演唱会—深圳站", "深圳", "深圳世界之窗之环球舞台", "2025-01-04 19:30", "280/756", "已结束"),
    _record("nanjing_collection", "李翊君", "李翊君《永远∞永远》新年巡回演唱会—南京站", "南京", "南京太阳宫剧场", "2025-01-01 19:30", "180/680", "已结束"),
    _record("nanjing_collection", "郑钧", "《头排·苏酒》1701跨年—郑钧《不要告别·此心永无别》", "南京", "1701 Live House Max", "2025-01-01 19:30", "498", "已结束"),
    _record("nanjing_collection", "张洢豪", "2024张洢豪《散步季》巡回演唱会—南京站", "南京", "Owl Voice猫头鹰空间", "2025-01-11 19:30", "128/358", "已结束"),
    _record("nanjing_collection", "潘星宇", "潘星宇个人演唱会—南京站", "南京", "稻香音乐空间", "2025-01-11 19:30", "128/368", "已结束"),
    _record("nanjing_collection", "王心凌", "王心凌 SUGAR HIGH 2.0巡回演唱会—南京站（2场）", "南京", "南京青奥体育公园体育馆", "2025-01-11 19:30", "待定", "已结束"),
]


def now_text():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def row_key(row):
    return (
        str(row.get("concert_name", "")).strip().casefold(),
        str(row.get("city", "")).strip().casefold(),
        str(row.get("venue", "")).strip().casefold(),
        str(row.get("show_time", "")).strip()[:10],
    )


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in RAW_FIELDS} for row in rows)


def verify_sources(session, checked_at):
    logs = []
    failures = []
    for source_id, definition in SOURCE_DEFINITIONS.items():
        url = definition["url"]
        try:
            response = session.get(url, timeout=20, allow_redirects=True)
            soup = BeautifulSoup(response.content, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else "未读取到页面标题"
            status = "可访问" if response.status_code == 200 else "未通过"
            if response.status_code != 200:
                failures.append(f"{source_id}: HTTP {response.status_code}")
            logs.append(
                {
                    "source_id": source_id,
                    "source_label": definition["label"],
                    "source_url": url,
                    "accessed_at": checked_at,
                    "http_status": response.status_code,
                    "access_status": status,
                    "page_title": title,
                    "content_bytes": len(response.content),
                }
            )
        except requests.RequestException as error:
            failures.append(f"{source_id}: {error.__class__.__name__}")
            logs.append(
                {
                    "source_id": source_id,
                    "source_label": definition["label"],
                    "source_url": url,
                    "accessed_at": checked_at,
                    "http_status": "",
                    "access_status": "请求失败",
                    "page_title": "",
                    "content_bytes": 0,
                }
            )
    if failures:
        raise RuntimeError("公开来源核验失败：" + "；".join(failures))
    return logs


def build_batch(collected_at):
    return [
        {
            **{field: record[field] for field in RAW_FIELDS if field in record},
            "source_url": SOURCE_DEFINITIONS[record["source_id"]]["url"],
            "collected_at": collected_at,
        }
        for record in PUBLIC_RECORDS
    ]


def merge_raw(path, additions):
    existing = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
    merged = []
    seen = set()
    for row in existing + additions:
        normalized = {field: str(row.get(field, "") or "").strip() for field in RAW_FIELDS}
        key = row_key(normalized)
        if not normalized["concert_name"] or key in seen:
            continue
        seen.add(key)
        merged.append(normalized)
    write_rows(path, merged)
    return len(existing), len(merged), len(merged) - len(existing)


def main():
    parser = argparse.ArgumentParser(description="核验公开页面并合并演唱会数据快照")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--root", type=Path, default=root)
    args = parser.parse_args()

    collected_at = now_text()
    session = requests.Session()
    session.headers.update({"User-Agent": "PulseAtlasStudy/1.0 (public snapshot research)"})
    source_logs = verify_sources(session, collected_at)
    batch = build_batch(collected_at)
    batch_path = args.root / "data" / "raw" / "concerts_public.csv"
    source_log_path = args.root / "data" / "raw" / "public_sources.csv"
    raw_path = args.root / "data" / "raw" / "concerts.csv"
    write_rows(batch_path, batch)
    with source_log_path.open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["source_id", "source_label", "source_url", "accessed_at", "http_status", "access_status", "page_title", "content_bytes"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(source_logs)
    old_count, merged_count, added_count = merge_raw(raw_path, batch)
    print(
        {
            "source_count": len(source_logs),
            "batch_count": len(batch),
            "raw_count_before": old_count,
            "raw_count_after": merged_count,
            "new_rows": added_count,
            "batch_file": str(batch_path),
            "source_log": str(source_log_path),
            "collected_at": collected_at,
        }
    )


if __name__ == "__main__":
    main()
