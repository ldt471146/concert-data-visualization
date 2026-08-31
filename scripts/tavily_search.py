# -*- coding: utf-8 -*-
"""Tavily 搜索辅助脚本。

用法（密钥从环境变量 TAVILY_KEYS 传入，多个用英文逗号分隔，脚本自动轮换）：
  TAVILY_KEYS="k1,k2" python scripts/tavily_search.py "查询词" [--max-results 8] [--out out.json]

设计说明：
- 密钥只从环境变量读取，不写入仓库文件。
- 请求体用 requests JSON 序列化，避免 Windows 终端中文编码问题。
- 遇到 429/401 自动轮换下一个密钥；全部失败时给出明确错误。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import requests

API_URL = "https://api.tavily.com/search"


def _keys() -> list[str]:
    raw = os.environ.get("TAVILY_KEYS", "").strip()
    if not raw:
        sys.exit("未提供 TAVILY_KEYS 环境变量")
    return [k.strip() for k in raw.split(",") if k.strip()]


def search(query: str, key: str, max_results: int, depth: str = "basic") -> dict:
    payload = {
        "query": query,
        "search_depth": depth,
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }
    resp = requests.post(
        API_URL,
        json=payload,
        headers={"Authorization": f"Bearer {key}"},
        timeout=40,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--out")
    parser.add_argument("--depth", default="basic")
    args = parser.parse_args()

    keys = _keys()
    last_error = None
    for i, key in enumerate(keys):
        try:
            data = search(args.query, key, args.max_results, args.depth)
            summary = {
                "query": args.query,
                "key_index": i,
                "count": len(data.get("results", [])),
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "score": r.get("score"),
                        "content": (r.get("content") or "")[:300],
                    }
                    for r in data.get("results", [])
                ],
            }
            if args.out:
                with open(args.out, "w", encoding="utf-8") as handle:
                    json.dump(summary, handle, ensure_ascii=False, indent=2)
            else:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1)
    sys.exit(f"所有密钥均失败，最后错误：{last_error}")


if __name__ == "__main__":
    main()