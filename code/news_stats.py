"""Crawl statistics comparable with results/bc6_taiwan.json -> crawl (report sections 3.3 and 7.1).

    python news_stats.py data/news_cnyes.jsonl data/prices/tw_trading_dates.csv results/news_stats.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "starter"))
from step1_prices import MEGA, MID  # noqa: E402
from step3_align import at  # noqa: E402

news, calendar, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
cal = pd.read_csv(calendar)["date"].tolist()
days = [pd.Timestamp(d).date() for d in cal]
closes = np.array([at(d, 13, 30) for d in days])
opens = np.array([at(d, 9, 0) for d in days])
lates = np.array([at(d, 8, 45) for d in days])

lines, seen, per_day = 0, set(), {}
b = {"over": 0, "sess": 0, "late": 0, "out": 0}
tagged = tags_total = 0
tagU1 = tagU1over = tagU2 = tagU2over = 0
U1, U2 = set(MEGA), set(MID)
with news.open(encoding="utf-8") as fh:
    for line in fh:
        x = json.loads(line)
        lines += 1
        per_day[x["_day"]] = per_day.get(x["_day"], 0) + 1
        if x["newsId"] in seen:
            continue
        seen.add(x["newsId"])
        t = int(x["publishAt"])
        j = int(np.searchsorted(closes, t, side="right"))
        k = "out" if j >= len(cal) else ("sess" if t >= opens[j] else ("late" if t >= lates[j] else "over"))
        b[k] += 1
        codes = {c for c in map(str, x.get("stock") or []) if c.isdigit()}
        if codes:
            tagged += 1
            tags_total += len(codes)
        if codes & U1:
            tagU1 += 1
            tagU1over += k == "over"
        if codes & U2:
            tagU2 += 1
            tagU2over += k == "over"

trading = set(cal)
res = {"lines": lines, "unique_newsId": len(seen), "dup": lines - len(seen), "days": len(per_day),
       "buckets": b, "share_over_pct": round(100 * b["over"] / len(seen), 1),
       "share_sess_pct": round(100 * b["sess"] / len(seen), 1), "share_late_pct": round(100 * b["late"] / len(seen), 1),
       "tagged": tagged, "tagged_share_pct": round(100 * tagged / len(seen), 1),
       "tags_per_tagged_item": round(tags_total / tagged, 2),
       "taggedU1": tagU1, "taggedU1over": tagU1over, "taggedU2": tagU2, "taggedU2over": tagU2over,
       "mean_items_per_trading_day": round(np.mean([v for d, v in per_day.items() if d in trading]), 1),
       "mean_items_per_non_trading_day": round(np.mean([v for d, v in per_day.items() if d not in trading]), 1)}
out.write_text(json.dumps(res, indent=2), encoding="utf-8")
print(json.dumps(res, indent=2))
