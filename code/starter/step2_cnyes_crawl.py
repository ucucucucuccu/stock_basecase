"""Step 2 (run on your own computer): download cnyes (鉅亨網) Taiwan-stock news day by day.

    pip install requests
    python step2_cnyes_crawl.py --start 2023-01-01 --end 2026-09-30 --out data/news_cnyes.jsonl

What we verified on 2026-10-18 (from a browser, not from this script):
- endpoint  https://api.cnyes.com/media/api/v1/newslist/category/tw_stock
- query     startAt / endAt (unix seconds) + page; 30 items per page regardless of `limit`
- history   returned items for dates back to 2014
- fields    newsId, publishAt (unix seconds), title, summary, content (HTML), stock (list of
            tickers such as "2330" or "US-NVDA"), market, keyword, categoryName, source ...
This is an undocumented API.  Keep the request rate low (default 1 request / second), keep the
raw text private (course use only), and stop if the site asks you to.
"""
import argparse
import datetime as dt
import html
import json
import re
import time
from pathlib import Path

import requests

BASE = "https://api.cnyes.com/media/api/v1/newslist/category/tw_stock"
HEADERS = {"User-Agent": "Mozilla/5.0 (course project; low-rate research crawler)",
           "Referer": "https://news.cnyes.com/", "Origin": "https://news.cnyes.com"}
TPE = dt.timezone(dt.timedelta(hours=8))
TAG = re.compile(r"<[^>]+>")


def strip(h):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", h or ""))).strip()


def day_items(session, day, delay):
    s = int(dt.datetime.combine(day, dt.time(0, 0), TPE).timestamp())
    e = s + 86399
    page, last, out = 1, 1, []
    while page <= last:
        r = session.get(BASE, params={"startAt": s, "endAt": e, "limit": 30, "page": page},
                        headers=HEADERS, timeout=30)
        r.raise_for_status()
        items = r.json()["items"]
        last = items.get("last_page", 1)
        for x in items.get("data", []):
            out.append({"newsId": x.get("newsId"), "publishAt": x.get("publishAt"),
                        "title": x.get("title"), "summary": x.get("summary"),
                        "content": strip(x.get("content")), "stock": x.get("stock") or [],
                        "market": x.get("market") or [], "keyword": x.get("keyword") or [],
                        "categoryName": x.get("categoryName"), "source": x.get("source")})
        page += 1
        time.sleep(delay)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default="data/news_cnyes.jsonl")
    ap.add_argument("--delay", type=float, default=1.0)
    a = ap.parse_args()
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():                      # resume: skip days already written
        with out.open(encoding="utf-8") as fh:
            for line in fh:
                done.add(json.loads(line)["_day"])
    day = dt.date.fromisoformat(a.start)
    end = dt.date.fromisoformat(a.end)
    failed = []
    with requests.Session() as sess, out.open("a", encoding="utf-8") as fh:
        while day <= end:
            if day.isoformat() not in done:
                items = None
                for attempt in range(3):
                    try:
                        items = day_items(sess, day, a.delay)
                        break
                    except Exception as e:
                        print(day, "attempt", attempt + 1, "failed:", e)
                        time.sleep(30 * (attempt + 1))
                if items is None:
                    failed.append(day.isoformat())
                else:
                    for x in items:
                        x["_day"] = day.isoformat()
                        fh.write(json.dumps(x, ensure_ascii=False) + "\n")
                    fh.flush()
                    print(day, len(items))
            day += dt.timedelta(days=1)
    if failed:
        print("days to retry later:", failed)
