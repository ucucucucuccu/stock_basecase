"""TAIEX daily open/close for the cross-market check (BC6 used the cnyes chart API, TWS:TSE01:INDEX).

    python fetch_taiex.py --start 2024-06-01 --end 2026-10-16 --out data/prices

Writes taiex_finmind.csv (FinMind TaiwanStockPrice, data_id TAIEX, 1 request) and taiex_yahoo.csv
(yfinance ^TWII) so the two sources can be compared.
"""
import argparse
import sys
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent / "starter"))
from step1_prices import finmind  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--start", default="2024-06-01"); ap.add_argument("--end", default="2026-10-16")
ap.add_argument("--out", default="data/prices")
a = ap.parse_args()
out = Path(a.out)
try:
    f = finmind("TaiwanStockPrice", a.start, a.end, "TAIEX").rename(columns={"max": "high", "min": "low"})
    f[["date", "open", "high", "low", "close"]].to_csv(out / "taiex_finmind.csv", index=False)
    print("FinMind TAIEX", len(f), "rows")
except Exception as e:  # FinMind may not serve the index on the free tier
    print("FinMind TAIEX failed:", e)
y = yf.download("^TWII", start=a.start, end=a.end, auto_adjust=False, progress=False, multi_level_index=False)
y.index = y.index.strftime("%Y-%m-%d")
y = y.rename(columns=str.lower).rename_axis("date").reset_index()
y[["date", "open", "high", "low", "close"]].to_csv(out / "taiex_yahoo.csv", index=False)
print("Yahoo ^TWII", len(y), "rows")
