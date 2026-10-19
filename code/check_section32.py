"""Re-check the Yahoo items of report section 3.2 against the FinMind files from step 1.

    python check_section32.py data/prices results/check_section32.json

Items: 2330 volume on 2026-10-14/15/16 (TWSE figures quoted in the report), the 0050 suspension
2025-06-11..06-17, the empty Yahoo row on 2025-08-01, the delisted 2888, and FinMind's no-trade
rows (all zero) that step 1 now drops.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

prices, out = Path(sys.argv[1]), Path(sys.argv[2])
TWSE_2330 = {"2026-10-14": 28111940, "2026-10-15": 58486711, "2026-10-16": 43046982}   # report 3.2


def yahoo(sym, start, end):
    y = yf.download(sym, start=start, end=end, auto_adjust=False, progress=False, multi_level_index=False)
    y.index = y.index.strftime("%Y-%m-%d")
    return y


res = {}
fm = pd.read_csv(prices / "tw_2330.csv").set_index("date")
y = yahoo("2330.TW", "2026-10-14", "2026-10-17")
res["2330_volume"] = {d: {"TWSE_report": v, "FinMind": int(fm.loc[d, "volume_raw"]) if d in fm.index else None,
                          "Yahoo": int(y.loc[d, "Volume"]) if d in y.index else None,
                          "Yahoo_vs_TWSE_pct": round(100 * (y.loc[d, "Volume"] / v - 1), 1) if d in y.index else None}
                      for d, v in TWSE_2330.items()}

y = yahoo("0050.TW", "2025-06-05", "2025-06-21")
res["0050_suspension_yahoo_rows"] = [{"date": d, "open": round(float(r.Open), 4), "high": round(float(r.High), 4),
                                      "low": round(float(r.Low), 4), "close": round(float(r.Close), 4),
                                      "volume": int(r.Volume)} for d, r in y.iterrows()]

y = yahoo("2330.TW", "2025-07-30", "2025-08-05")
res["2330_yahoo_around_2025-08-01"] = {d: None if pd.isna(r.Close) else round(float(r.Close), 2) for d, r in y.iterrows()}
res["2330_yahoo_has_2025-08-01_row"] = "2025-08-01" in y.index and not pd.isna(y.loc["2025-08-01", "Close"])

y = yahoo("2888.TW", "2024-06-01", "2025-08-01")
res["2888_yahoo_rows"] = int(len(y))
res["2888_finmind_rows"] = int(len(pd.read_csv(prices / "tw_2888.csv")))

q = pd.read_csv(prices / "_quality_report_tw.csv", dtype=str).fillna("")
if "dropped_no_trade_rows" in q:
    res["finmind_no_trade_rows_dropped"] = {r.code: r.dropped_no_trade_rows for r in q.itertuples() if r.dropped_no_trade_rows}

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(res, indent=2, ensure_ascii=False))
