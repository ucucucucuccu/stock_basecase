"""Step 3: attach every news item to the trading day it can legitimately be used for.

    python step3_align.py --news data/news_cnyes.jsonl --calendar data/prices/0050.TW.csv \
                          --out data/news_buckets.csv
    python step3_align.py --selftest

Buckets for trading day d (p = previous trading day), Taipei time:
    prev_session  [p 09:00, p 13:30)   known at p's close   -> usable for close(p)->close(d)
    overnight     [p 13:30, d 08:45)   known before d opens -> usable for open(d)->close(d)
    late          [d 08:45, d 09:00)   too late to act on at the open; kept separate
    session       [d 09:00, d 13:30)   concurrent with d    -> NEVER a predictor for day d
Weekend and holiday news falls into the overnight bucket of the next trading day.

Timestamps: cnyes `publishAt` is unix seconds.  FinMind TaiwanStockNews `date` strings are UTC
(checked 2026-10-19 against cnyes publishAt: the same article is exactly 8 hours earlier in
FinMind).  Read them with finmind_utc_to_unix(); treating them as Taipei time would move
after-close articles (13:30-16:00) into the pre-open window of the same day - a direct leak.
"""
import argparse
import bisect
import datetime as dt
import json
import re

import pandas as pd

TPE = dt.timezone(dt.timedelta(hours=8))
REACTION = re.compile(r"(漲停|跌停|大漲|大跌|勁揚|重挫|走高|走低|翻紅|翻黑|收盤|收紅|收黑|漲幅|跌幅|"
                      r"創高|新高|新低|領漲|領跌|急漲|急跌|收漲|收跌|週漲|週跌|漲逾|跌逾|攻上|站上|跌破|"
                      r"失守|買超|賣超)")  # rough first pass; replace with a classifier trained on labels


def finmind_utc_to_unix(s):
    """'2026-10-15 08:24:21' (UTC, as FinMind returns it) -> unix seconds"""
    return int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp())


def at(day, hh, mm):
    return int(dt.datetime.combine(day, dt.time(hh, mm), TPE).timestamp())


def bucketize(publish_at, days):
    """Return (trading_day, bucket) for a unix timestamp, given sorted trading days."""
    closes = [at(d, 13, 30) for d in days]
    j = bisect.bisect_right(closes, publish_at)        # first day whose close is after the item
    if j >= len(days):
        return None, None
    d = days[j]
    if publish_at >= at(d, 9, 0):
        return d, "session"
    if publish_at >= at(d, 8, 45):
        return d, "late"
    # before d's 08:45: either yesterday afternoon/evening, a weekend/holiday, or early morning
    if j > 0 and publish_at < at(days[j - 1], 13, 30):  # cannot happen given bisect, kept as guard
        return days[j - 1], "session"
    return d, "overnight"


def prev_session_rows(df, days):
    """The 'session' bucket of day p is the 'prev_session' bucket of the next trading day."""
    nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    s = df[df.bucket == "session"].copy()
    s["trading_day"] = s["trading_day"].map(nxt)
    s["bucket"] = "prev_session"
    return s.dropna(subset=["trading_day"])


def align(news_rows, days):
    rows = []
    for x in news_rows:
        d, b = bucketize(int(x["publishAt"]), days)
        if d is None:
            continue
        tags = [t for t in x.get("stock", []) if re.fullmatch(r"\d{4,6}", str(t))]
        for tag in (tags or ["_MARKET_"]):
            rows.append({"trading_day": d, "bucket": b, "stock": tag, "newsId": x["newsId"],
                         "publishAt": x["publishAt"], "n_tags": len(tags),
                         "reaction_title": bool(REACTION.search(x.get("title") or ""))})
    df = pd.DataFrame(rows)
    return pd.concat([df, prev_session_rows(df, days)], ignore_index=True)


def selftest():
    # real 2026 calendar: Fri 10/9 was the National Day holiday (10/10 fell on a Saturday)
    days = [dt.date(2026, 10, 7), dt.date(2026, 10, 8), dt.date(2026, 10, 12), dt.date(2026, 10, 13)]
    T = lambda m, d, hh, mm: dt.datetime(2026, m, d, hh, mm, tzinfo=TPE)
    cases = [  # (description, publish time, expected day, expected bucket)
        ("Thu 10/8 07:30", T(10, 8, 7, 30), days[1], "overnight"),
        ("Thu 10/8 08:50", T(10, 8, 8, 50), days[1], "late"),
        ("Thu 10/8 10:00", T(10, 8, 10, 0), days[1], "session"),
        ("Thu 10/8 13:30 (the close)", T(10, 8, 13, 30), days[2], "overnight"),
        ("Thu 10/8 20:00", T(10, 8, 20, 0), days[2], "overnight"),
        ("Fri 10/9 holiday 12:00", T(10, 9, 12, 0), days[2], "overnight"),
        ("Sat 10/10 National Day", T(10, 10, 9, 0), days[2], "overnight"),
        ("Mon 10/12 07:00", T(10, 12, 7, 0), days[2], "overnight"),
    ]
    ok = True
    for desc, t, d_exp, b_exp in cases:
        d, b = bucketize(int(t.timestamp()), days)
        flag = (d == d_exp and b == b_exp)
        ok &= flag
        print(f"{'OK ' if flag else 'BAD'} {desc:30s} -> {d} {b}")
    # FinMind UTC string: 08:24:21 UTC is 16:24:21 Taipei, i.e. after the 10/15 close
    u = finmind_utc_to_unix("2026-10-15 08:24:21")
    tpe = dt.datetime.fromtimestamp(u, TPE)
    flag = tpe.strftime("%Y-%m-%d %H:%M") == "2026-10-15 16:24"
    ok &= flag
    print(f"{'OK ' if flag else 'BAD'} FinMind UTC conversion       -> {tpe:%Y-%m-%d %H:%M} Taipei")
    rows = [{"newsId": 1, "publishAt": int(cases[2][1].timestamp()), "stock": ["2330", "US-NVDA"],
             "title": "台積電盤中走高"}]
    df = align(rows, days)
    print(df.to_string(index=False))
    ok &= set(df.bucket) == {"session", "prev_session"} and set(df.trading_day) == {days[1], days[2]}
    print("selftest", "passed" if ok else "FAILED")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--news"); ap.add_argument("--calendar"); ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(0 if selftest() else 1)
    cal = pd.read_csv(a.calendar, index_col=0, parse_dates=True)
    days = sorted({ts.date() for ts in cal.index})
    with open(a.news, encoding="utf-8") as fh:
        news = [json.loads(l) for l in fh]
    out = align(news, days)
    out.to_csv(a.out, index=False)
    print(out.groupby("bucket").size())
