"""Supplement to step 4: the BC6 numbers that step4_baseline_models.py does not output.

    python step4_supplement.py --prices data/prices --news data/news_cnyes.jsonl --universe mid \
        --taiex data/prices/taiex.csv --out results/step4_supplement_mid.json

Builds the same (stock, day) table as step 4 (same code path) and adds
  1. event-day subsets: Delta R2 (M1e - M1) with a 95% interval from bootstrapping test DAYS
     (report 7.1 table B, "+0.103 (+0.050 to +0.157)"); step 4 gives only the point values;
  2. the leakage control (same-day session news, LEAK = M2 + l_sess) with alpha held equal to M2's,
     in the fixed split and in the walk-forward (report 7.1 table C, "+0.012 (+0.008 to +0.015)");
     step 4 picks LEAK's alpha separately on the validation quarter, which adds selection noise;
  3. cross-market (report 7.1 table C): US overnight returns -> TAIEX opening gap and open-to-close,
     TSM ADR -> 2330, with the BC6 formulas (OLS fit 2024-10..2025-09, test 2025-10..2026-09).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

sys.path.insert(0, str(Path(__file__).resolve().parent / "starter"))
import step4_baseline_models as s4  # noqa: E402
from step1_prices import MEGA, MID  # noqa: E402


def build(folder, news, codes, start, end):
    """the table D of step4_baseline_models.main(), unchanged"""
    cal, px = s4.load_prices(folder, codes)
    us = s4.us_features(folder, cal)
    nf = s4.news_features(news, cal, codes)
    idx_d = pd.read_csv(folder / "tw_trading_dates.csv")["date"]
    gapdays = pd.Series(pd.to_datetime(idx_d).diff().dt.days.values, index=cal)
    mk = pd.concat([px[c].y_tr for c in codes], axis=1).mean(axis=1)
    frames = []
    for i, c in enumerate(codes):
        d = px[c].join(us).join(nf[c])
        d["mk1"] = mk.shift(1); d["mk5"] = s4.lag_mean(mk, 1, 5); d["gapdays"] = gapdays
        d["code"] = c; d["ci"] = i
        frames.append(d.reset_index().rename(columns={"index": "date"}))
    D = pd.concat(frames, ignore_index=True)
    D = D[(D.date >= start) & (D.date <= end)]
    F0 = ["hd", "hw", "hm"]
    F1 = F0 + ["mk1", "mk5", "gapdays", "abv1", "abs_usix", "abs_ussox", "usrngix", "usrngsox", "abs_ustsm", "usn"]
    F2 = F1 + ["l_over", "any_over", "l_prev", "l_mover", "l_mprev"]
    F3 = F2 + ["l_" + k for k in s4.FLAGS]
    D = D.dropna(subset=F3 + ["y_tr", "y_abv", "tr_raw", "abv5"]).reset_index(drop=True)
    D = D[~D.is_event_day.astype(bool)].reset_index(drop=True)
    specs = {"M0": F0, "M1": F1, "M2": F2, "M3": F3, "M1e": F1 + ["l_earn", "l_rev"], "LEAK": F2 + ["l_sess"]}
    return cal, us, D, specs


def walkforward_preds(D, specs, test_start, alpha=10.0):
    """same refits as step4 walkforward(): monthly expanding window, alpha fixed"""
    y = D.y_tr.values
    months = sorted(D.loc[D.date > test_start, "date"].str[:7].unique())
    dummies = pd.get_dummies(D.code, dtype=float).values
    pred = {n: np.full(len(D), np.nan) for n in specs}
    for m in months:
        fit = (D.date < m + "-01").values
        now = (D.date.str[:7] == m).values
        for n, cols in specs.items():
            X = D[cols].astype(float).values
            mu, sd = X[fit].mean(0), X[fit].std(0) + 1e-9
            Z = np.hstack([(X - mu) / sd, dummies])
            pred[n][now] = Ridge(alpha=alpha).fit(Z[fit], y[fit]).predict(Z[now])
    return pred


def day_boot(dates, fn, rng, reps):
    ud = np.unique(dates)
    rows_of = {d: np.where(dates == d)[0] for d in ud}
    v = [fn(np.concatenate([rows_of[d] for d in rng.choice(ud, len(ud))])) for _ in range(reps)]
    return [round(float(x), 4) for x in np.percentile(v, [2.5, 97.5])]


def ols_eval(fit_df, te_df, xcols, ycol):
    """BC6 __models/__extra: OLS with intercept on the fit period; R2 against the fit-period mean;
    direction accuracy = sign(prediction) == sign(actual)"""
    X = np.column_stack([np.ones(len(fit_df))] + [fit_df[c].values for c in xcols])
    w = np.linalg.lstsq(X, fit_df[ycol].values, rcond=None)[0]
    Xt = np.column_stack([np.ones(len(te_df))] + [te_df[c].values for c in xcols])
    p, yt = Xt @ w, te_df[ycol].values
    ym = fit_df[ycol].mean()
    return {"r2": round(float(1 - np.sum((yt - p) ** 2) / np.sum((yt - ym) ** 2)), 4),
            "dirAcc": round(float((np.sign(p) == np.sign(yt)).mean()), 4), "n": int(len(te_df)),
            "coef": [round(float(v), 4) for v in w]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="data/prices"); ap.add_argument("--news", default="data/news_cnyes.jsonl")
    ap.add_argument("--universe", choices=["mega", "mid"], required=True)
    ap.add_argument("--start", default="2024-10-01"); ap.add_argument("--train-end", default="2025-06-30")
    ap.add_argument("--val-end", default="2025-09-30"); ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--taiex", nargs="*", default=[], help="CSV files with date, open, close of the TAIEX index")
    ap.add_argument("--reps", type=int, default=1000); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    folder = Path(a.prices)
    codes = [c for c in (MEGA if a.universe == "mega" else MID) if (folder / f"tw_{c}.csv").exists()]
    cal, us, D, specs = build(folder, a.news, codes, a.start, a.end)
    rng = np.random.default_rng(1)
    res = {"universe": a.universe, "n_rows": int(len(D))}

    # 1 + 2 (walk-forward): event subsets with intervals, leakage control
    P = walkforward_preds(D, {k: specs[k] for k in ["M1", "M2", "M1e", "LEAK"]}, a.val_end)
    te = ~np.isnan(P["M1"])
    yt = D.y_tr.values[te]; dates = D.date.values[te]; sub = D[te]
    bench = sub.groupby("code")["y_tr"].transform("mean").values
    Pt = {n: p[te] for n, p in P.items()}

    def r2(p, r):
        return 1 - np.sum((yt[r] - p[r]) ** 2) / np.sum((yt[r] - bench[r]) ** 2)

    er = ((sub.l_earn > 0) | (sub.l_rev > 0)).values
    groups = {"earnings_or_revenue_news": er, "other_news": ((sub.any_over > 0) & ~er).values,
              "no_news": (sub.any_over == 0).values, "all": np.ones(len(sub), bool)}
    wf = {}
    for g, mask in groups.items():
        f = lambda r, m=mask: r2(Pt["M1e"], r[m[r]]) - r2(Pt["M1"], r[m[r]])
        idx = np.where(mask)[0]
        wf[g] = {"n": int(mask.sum()), "M1_r2_within": round(float(r2(Pt["M1"], idx)), 4),
                 "M1e_r2_within": round(float(r2(Pt["M1e"], idx)), 4),
                 "delta_M1e_minus_M1": {"value": round(float(f(np.arange(len(yt)))), 4), "ci95": day_boot(dates, f, rng, a.reps)}}
    f = lambda r: r2(Pt["LEAK"], r) - r2(Pt["M2"], r)
    wf["leak_session_news_delta_LEAK_minus_M2"] = {"value": round(float(f(np.arange(len(yt)))), 4),
                                                    "ci95": day_boot(dates, f, rng, a.reps)}
    res["walkforward_alpha10"] = wf

    # 2 (fixed split): LEAK with the same alpha as M2, R2 against each stock's fit-period mean (as in step 4)
    tr = (D.date <= a.train_end).values; va = ((D.date > a.train_end) & (D.date <= a.val_end)).values
    fit = tr | va; tem = (D.date > a.val_end).values
    dummies = pd.get_dummies(D.code, dtype=float).values
    y = D.y_tr.values
    bench_f = D.code.map(D[fit].groupby("code")["y_tr"].mean()).values

    def design(cols):
        X = D[cols].astype(float).values
        mu, sd = X[fit].mean(0), X[fit].std(0) + 1e-9
        return np.hstack([(X - mu) / sd, dummies])

    X2, XL = design(specs["M2"]), design(specs["LEAK"])
    al = min([0.1, 1, 10, 100, 1000, 10000],
             key=lambda v: np.mean((Ridge(alpha=v).fit(X2[tr], y[tr]).predict(X2[va]) - y[va]) ** 2))
    p2 = Ridge(alpha=al).fit(X2[fit], y[fit]).predict(X2)[tem]
    pl = Ridge(alpha=al).fit(XL[fit], y[fit]).predict(XL)[tem]
    yf, bf, df = y[tem], bench_f[tem], D.date.values[tem]
    f = lambda r: (np.sum((yf[r] - p2[r]) ** 2) - np.sum((yf[r] - pl[r]) ** 2)) / np.sum((yf[r] - bf[r]) ** 2)
    res["fixed_split_leak_same_alpha"] = {"alpha_M2_and_LEAK": al, "delta_LEAK_minus_M2": round(float(f(np.arange(len(yf)))), 4),
                                          "ci95": day_boot(df, f, rng, a.reps)}

    # 3: cross-market, BC6 formulas
    U = us.copy()
    for c in ["usix", "ussox", "ustsm"]:
        U[c] = U[c].fillna(0.0)                      # BC6: no US session in between -> 0
    cm = {}
    for path in a.taiex:
        t = pd.read_csv(path).set_index("date").reindex(cal)
        g = pd.DataFrame({"gap": np.log(t.open / t.close.shift(1)), "oc": np.log(t.close / t.open)}, index=cal).join(U)
        g = g[(g.index >= a.start) & (g.index <= a.end)].dropna(subset=["gap", "oc"])
        fit_g, te_g = g[g.index <= a.val_end], g[g.index > a.val_end]
        cm[Path(path).stem] = {"gap": ols_eval(fit_g, te_g, ["usix", "ussox", "ustsm"], "gap"),
                               "oc": ols_eval(fit_g, te_g, ["usix", "ussox", "ustsm"], "oc")}
    if "2330" in codes:
        t = D[D.code == "2330"].copy()
        t["gap"] = np.log(t.open / t.ref_prev_close)
        t = t.dropna(subset=["gap", "oc", "ustsm"])
        fit_t, te_t = t[t.date <= a.val_end], t[t.date > a.val_end]
        cm["adr_TSM_to_2330"] = {"gap": ols_eval(fit_t, te_t, ["ustsm"], "gap"), "oc": ols_eval(fit_t, te_t, ["ustsm"], "oc")}
    res["cross_market"] = cm

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
