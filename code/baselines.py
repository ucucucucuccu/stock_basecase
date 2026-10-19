"""Baselines for the main target (log true range): how much do HAR (M0) and HAR + market + US
overnight (M1) beat naive forecasts?  Same (stock, day) table and test period as step 4 / BC6.

    python code/baselines.py --prices data/prices --universe mid  --out results/baselines_mid.json
    python code/baselines.py --prices data/prices --universe mega --out results/baselines_mega.json

Forecasts for trading day d, all made with information available at 08:45 on day d:
  mean_past   the stock's average log TR over all earlier rows (refreshed monthly, like the refits)
  yesterday   log TR of day d-1 (random-walk / persistence forecast)
  mean5       average log TR over d-5 .. d-1
  mean22      average log TR over d-22 .. d-1
  ewma        exponentially weighted average of past log TR (RiskMetrics-style lambda = 0.94)
  M0_HAR      ridge on (yesterday, mean5, mean22) + stock dummies, monthly expanding refit, alpha 10
  M1          M0 + market HAR, calendar gap, previous-day abnormal volume, US overnight returns/ranges

Two R2 definitions are reported:
  r2_within   against each stock's own test-period mean (as in step 4 and BC6; measures how much of
              the day-to-day variation within a stock is explained; uses the test mean, so it is strict)
  r2_os       1 - MSE(model) / MSE(mean_past): the usual out-of-sample R2 against the historical mean
95% intervals: bootstrap over test days.  News features are not needed; without --news an empty news
file is used, which gives exactly the same rows as step 4 (news counts only enter M2/M3).
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "starter"))
sys.path.insert(0, str(HERE))
import step4_baseline_models as s4  # noqa: E402
from step1_prices import MEGA, MID  # noqa: E402
from step4_supplement import build, day_boot, walkforward_preds  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="data/prices")
    ap.add_argument("--news", default=None, help="optional; only needed for identical row filtering")
    ap.add_argument("--universe", choices=["mega", "mid"], required=True)
    ap.add_argument("--start", default="2024-10-01")
    ap.add_argument("--val-end", default="2025-09-30")
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--lam", type=float, default=0.94)
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    folder = Path(a.prices)
    codes = [c for c in (MEGA if a.universe == "mega" else MID) if (folder / f"tw_{c}.csv").exists()]
    news = a.news
    if news is None:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        tmp.close()
        news = tmp.name
    _, _, D, specs = build(folder, news, codes, a.start, a.end)

    # EWMA of past log TR, from each stock's full price history (not only the modelling rows)
    _, px = s4.load_prices(folder, codes)
    ew = {c: px[c].y_tr.shift(1).ewm(alpha=1 - a.lam, adjust=False, ignore_na=True).mean() for c in codes}
    D["ewma"] = [ew[c].get(d, np.nan) for c, d in zip(D.code, D.date)]

    P = walkforward_preds(D, {"M0_HAR": specs["M0"], "M1": specs["M1"]}, a.val_end)
    te = ~np.isnan(P["M1"])

    # mean_past: the stock's mean over all rows before the forecast month (same information as the refits)
    mp = np.full(len(D), np.nan)
    for m in sorted(D.loc[te, "date"].str[:7].unique()):
        hist = D[D.date < m + "-01"].groupby("code")["y_tr"].mean()
        now = (D.date.str[:7] == m).values & te
        mp[now] = D.loc[now, "code"].map(hist).values

    sub = D[te]
    preds = {"mean_past": mp[te], "yesterday": sub.hd.values, "mean5": sub.hw.values,
             "mean22": sub.hm.values, "ewma": sub.ewma.values,
             "M0_HAR": P["M0_HAR"][te], "M1": P["M1"][te]}
    yt, dates = sub.y_tr.values, sub.date.values
    bench = sub.groupby("code")["y_tr"].transform("mean").values
    rng = np.random.default_rng(1)

    def r2_within(p, r):
        return 1 - np.sum((yt[r] - p[r]) ** 2) / np.sum((yt[r] - bench[r]) ** 2)

    def r2_os(p, r):
        return 1 - np.sum((yt[r] - p[r]) ** 2) / np.sum((yt[r] - preds["mean_past"][r]) ** 2)

    allr = np.arange(len(yt))
    res = {"universe": a.universe, "n_test": int(len(yt)), "n_test_days": int(len(np.unique(dates))),
           "test_period": f"{a.val_end} < date <= {a.end}", "models": {}}
    for n, p in preds.items():
        if np.isnan(p).any():
            raise RuntimeError(f"{n}: {int(np.isnan(p).sum())} missing forecasts")
        res["models"][n] = {
            "r2_within": round(float(r2_within(p, allr)), 4),
            "r2_within_ci95": day_boot(dates, lambda r, p=p: r2_within(p, r), rng, a.reps),
            "r2_os": round(float(r2_os(p, allr)), 4),
            "rmse_log_tr": round(float(np.sqrt(np.mean((yt - p) ** 2))), 4)}
    for base in ["yesterday", "mean22", "ewma"]:
        f = lambda r, b=preds[base]: r2_within(preds["M0_HAR"], r) - r2_within(b, r)
        res[f"delta_M0_HAR_minus_{base}"] = {"value": round(float(f(allr)), 4), "ci95": day_boot(dates, f, rng, a.reps)}
    f = lambda r: r2_within(preds["M1"], r) - r2_within(preds["M0_HAR"], r)
    res["delta_M1_minus_M0_HAR"] = {"value": round(float(f(allr)), 4), "ci95": day_boot(dates, f, rng, a.reps)}

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
