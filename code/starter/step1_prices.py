"""Step 1 (run on your own computer): Taiwan prices from FinMind (TWSE official numbers),
US overnight data from yfinance, plus the data checks found necessary in BC6.

    pip install requests pandas "yfinance>=1.7"
    python step1_prices.py --start 2024-06-01 --end 2026-10-16 --out data/prices
    python step1_prices.py ... --yahoo-check        # also compare Taiwan stocks with Yahoo

Why not yfinance for Taiwan stocks (checked on 2026-10-19, see report section 3.2):
- Yahoo daily volume for 2330 was about 20% below the TWSE figure on the days checked;
  FinMind and the cnyes chart API matched TWSE exactly.
- Yahoo filled the 0050 suspension (2025-06-11..06-17, 1-to-4 split) with flat rows and zero
  volume, and had an empty row for most stocks on 2025-08-01.
yfinance is still fine for US indices and ADRs (cnyes was missing days such as 2025-04-09).

FinMind limits: 300 requests/hour without a token, 600 with a free registered token
(set the environment variable FINMIND_TOKEN).  This script uses about 3 requests per stock,
about 180 for both universes, so one run fits in the free limit; register for a token if you
rerun within the same hour.
"""
import argparse
import os
import time
from pathlib import Path

import pandas as pd
import requests

FM = "https://api.finmindtrade.com/api/v4/data"
# The two universes used in BC6.  MEGA: large caps by market value around 2024.  MID: codes
# outside MEGA whose pre-market news share in 2024-10..2025-09 was 10-60% (top 40 by that
# share).  Decide your own lists with information available at the start of the test period.
MEGA = ["2330", "2317", "2454", "2308", "2382", "2881", "2891", "2882", "2412", "3711",
        "2303", "2886", "2884", "2357", "1216", "2885", "3231", "2892", "2345", "6669"]
MID = ["2609", "2603", "3037", "3017", "4979", "2383", "3008", "3661", "2615", "2002",
       "2618", "2356", "3324", "3450", "3481", "2408", "4958", "3081", "3406", "2610",
       "8046", "3363", "3019", "2887", "2368", "2888", "2324", "4938", "1815", "2883",
       "3443", "2344", "1101", "2327", "2374", "3189", "3665", "4931", "2409", "3163"]
# 2888 was delisted in 2025 (merged into 2887): keep it, otherwise the sample has survivorship bias.
# Some MID codes trade on TPEx (Yahoo suffix .TWO): 1815 3081 3163 3324 3363 4931 4979.
TPEX = {"1815", "3081", "3163", "3324", "3363", "4931", "4979"}
US = ["^IXIC", "^SOX", "^GSPC", "^VIX", "TSM", "NVDA"]


def finmind(dataset, start, end=None, data_id=None):
    params = {"dataset": dataset, "start_date": start}
    if end:
        params["end_date"] = end
    if data_id:
        params["data_id"] = data_id
    headers = {}
    if os.environ.get("FINMIND_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["FINMIND_TOKEN"]
    for attempt in range(4):
        r = requests.get(FM, params=params, headers=headers, timeout=60)
        if r.status_code == 200 and r.json().get("status") == 200:
            return pd.DataFrame(r.json()["data"])
        print(dataset, data_id, "attempt", attempt + 1, r.status_code, r.text[:120])
        time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"FinMind failed: {dataset} {data_id}")


def split_like_events(frames, threshold=1.5):
    """Reference-price events whose before/after price ratio exceeds `threshold`: the share
    count changed (split, par-value change, very large stock dividend), so volume must be
    rescaled.  Ordinary cash dividends have ratios around 1.01-1.10 and are ignored."""
    ref, events = {}, []
    for df in frames:
        if len(df) and "after_price" in df:
            before = df["before_price"] if "before_price" in df else df["after_price"]
            for d, b, p in zip(df["date"], before, df["after_price"]):
                b, p = float(b), float(p)
                ref[d] = p
                if p > 0 and b / p > threshold:
                    events.append((d, b / p))
    return ref, events


def tw_stock(code, start, end, calendar):
    px = finmind("TaiwanStockPrice", start, end, code)
    if len(px) == 0:
        print(code, "no price rows from FinMind (delisted before the start date, or a wrong code)")
        return None, {"code": code, "rows": 0}
    px = px.rename(columns={"max": "high", "min": "low", "Trading_Volume": "volume"})
    px = px[["date", "open", "high", "low", "close", "volume"]].sort_values("date").reset_index(drop=True)
    # no-trade rows: FinMind returns O=H=L=C=0 with volume 0 on days a stock did not trade (e.g. 2317
    # on 2025-07-30).  Drop them (checklist 3.5 item 2), otherwise the true range is infinite and the
    # next day's previous close is 0.  Limit-locked days have volume > 0 and are kept.
    no_trade = (px.volume <= 0) & (px.open == px.high) & (px.high == px.low) & (px.low == px.close)
    dropped = px.date[no_trade].tolist()
    px = px[~no_trade].reset_index(drop=True)
    time.sleep(1.2)
    div = finmind("TaiwanStockDividendResult", start, end, code)
    time.sleep(1.2)
    spl = finmind("TaiwanStockSplitPrice", start, end, code)
    time.sleep(1.2)
    # reference previous close: on ex-right/ex-dividend/split days use the exchange's
    # reference price (after_price) instead of yesterday's close
    ref, vol_events = split_like_events((div, spl))
    # volume before a split is expressed in post-split shares (otherwise abnormal volume jumps)
    px["volume_raw"] = px["volume"]
    px["volume"] = px["volume"].astype(float)
    for d, ratio in vol_events:
        px.loc[px["date"] < d, "volume"] *= ratio
    px["prev_close"] = px["close"].shift(1)
    px["is_event_day"] = px["date"].isin(ref.keys())
    px["ref_prev_close"] = [ref.get(d, pc) for d, pc in zip(px["date"], px["prev_close"])]
    # checks
    flat = (px.high == px.low)
    # Taiwan's daily price limit is +-10% of the reference price, so close / reference stays in
    # [0.9, 1.1] up to tick rounding.  Outside that range = a data error, or a capital reduction /
    # split missing from FinMind's tables (e.g. 3481 on 2024-08-26: add its reference price from
    # TaiwanStockCapitalReductionReferencePrice).  A log-return threshold of 0.105 is not used
    # because it flags every ordinary limit-down day (ln 0.9 = -0.1054).
    ratio = px.close / px.ref_prev_close
    outside = (ratio < 0.899) | (ratio > 1.101)
    missing = sorted(set(calendar) - set(px.date))
    report = {"code": code, "rows": len(px), "missing_trading_days": len(missing),
              "missing_list": ",".join(missing[:10]), "zero_volume": int((px.volume <= 0).sum()),
              "dropped_no_trade_rows": ",".join(dropped),
              "high_eq_low_days": int(flat.sum()),            # limit-locked days are real (e.g. 2025-04-07)
              "event_days": int(px.is_event_day.sum()),
              "volume_rescaled_events": ";".join(f"{d}x{r:.3f}" for d, r in vol_events),
              "outside_10pct_limit": int(outside.sum()),
              "outside_10pct_limit_dates": ",".join(px.date[outside].tolist()[:10])}
    return px, report


def yahoo_check(codes, start, end, fm_frames):
    import yfinance as yf
    rows = []
    for c in codes:
        y = yf.download(f"{c}{'.TWO' if c in TPEX else '.TW'}", start=start, end=end, auto_adjust=False, progress=False,
                        multi_level_index=False)
        y.index = y.index.strftime("%Y-%m-%d")
        f = fm_frames[c].set_index("date")
        both = f.join(y[["Volume", "Open", "High", "Low", "Close"]], how="inner")
        fake = ((y.Open == y.High) & (y.High == y.Low) & (y.Low == y.Close) & (y.Volume == 0)).sum()
        rows.append({"code": c, "yahoo_rows": len(y), "finmind_rows": len(f),
                     "only_in_yahoo": len(set(y.index) - set(f.index)),
                     "only_in_finmind": len(set(f.index) - set(y.index)),
                     "median_volume_ratio_yahoo_over_finmind": round(float((both.Volume / both.volume).median()), 3),
                     "yahoo_flat_zero_volume_rows": int(fake)})
        time.sleep(1.5)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-06-01")
    ap.add_argument("--end", default="2026-10-16")
    ap.add_argument("--out", default="data/prices")
    ap.add_argument("--yahoo-check", action="store_true")
    ap.add_argument("--universe", choices=["mega", "mid", "both"], default="both")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    cal = finmind("TaiwanStockTradingDate", a.start, a.end)["date"].tolist()
    cal = [d for d in cal if a.start <= d <= a.end]
    pd.Series(cal, name="date").to_csv(out / "tw_trading_dates.csv", index=False)

    TW = {"mega": MEGA, "mid": MID, "both": MEGA + MID}[a.universe]
    reports, frames = [], {}
    for code in TW:
        px, rep = tw_stock(code, a.start, a.end, cal)
        if px is None:
            reports.append(rep)
            continue
        px.to_csv(out / f"tw_{code}.csv", index=False)
        frames[code] = px
        reports.append(rep)
        print(rep)
    pd.DataFrame(reports).to_csv(out / "_quality_report_tw.csv", index=False)

    import yfinance as yf
    for s in US:
        df = yf.download(s, start=a.start, end=a.end, auto_adjust=True, progress=False, multi_level_index=False)
        df.to_csv(out / f"us_{s.replace('^', 'IDX_')}.csv")
        print(s, len(df), "rows")
        time.sleep(1.5)

    if a.yahoo_check:
        chk = yahoo_check([c for c in TW if c in frames and c != "2888"][:5], a.start, a.end, frames)
        chk.to_csv(out / "_yahoo_vs_finmind.csv", index=False)
        print(chk.to_string(index=False))
