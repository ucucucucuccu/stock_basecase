"""BC5: on the same StockNet data as BC3, predict HOW MUCH a stock moves instead of WHICH WAY.

Targets for trading day d (all observed after the open, predicted with information known before it)
  logrange  log of ln(High/Low): intraday range, a standard volatility proxy (Parkinson 1980)
  big       1 if ln(High/Low) is in the top 10% of that stock's own training-period ranges
  abvol     log volume minus the mean log volume of the previous 20 trading days
  dir       sign of the open-to-close return (negative control, see BC3)

Nested models (ridge, alpha chosen on the validation quarter, refit on train+validation)
  M0  HAR: the stock's own log range at lags 1, mean 2-5, mean 6-22 (+ stock dummies)
  M1  M0 + market HAR + calendar (gap length) + previous-day |return| and abnormal volume
  M2  M1 + tweet COUNTS known before the open (overnight, previous session, market-wide)
  M3  M2 + tweet TEXT (TF-IDF of overnight tweets)
  LEAK  M2 + tweet count during day d's own session (published while the target happens)

Split: train 2014-01..2015-03, validation 2015-04..06, test 2015-07..12 (time order).
Uncertainty: 95% intervals from bootstrapping test DAYS (all stocks of a day move together).

Usage:  python3 -I bc5_stocknet_volatility.py <stocknet_dir> <results_dir>
"""
import bisect
import datetime as dt
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score

SN = Path(sys.argv[1])
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "results")
OUT.mkdir(parents=True, exist_ok=True)
ET = ZoneInfo("America/New_York")
rng = np.random.default_rng(5)
DROP = {"AGFS", "GMRE", "SPLP"}
START, END = pd.Timestamp("2014-02-03"), pd.Timestamp("2015-12-31")
TRAIN_END, VAL_END = pd.Timestamp("2015-03-31"), pd.Timestamp("2015-06-30")
STOP = {"AT_USER", "URL", "rt", "$", "-", ":", ".", ",", "!", "?", "#"}

# ------------------------------------------------------------------ prices and targets
frames = []
for f in sorted((SN / "price/raw").glob("*.csv")):
    tic = f.stem
    if tic in DROP or not (SN / "tweet/preprocessed" / tic).exists():
        continue
    d = pd.read_csv(f, parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    d = d[(d.High > 0) & (d.Low > 0) & (d.Volume > 0)].reset_index(drop=True)
    lr = np.log(d.High / d.Low).clip(lower=1e-4)
    d["tic"] = tic
    d["logrange"] = np.log(lr)
    d["range"] = lr
    d["absret_prev"] = (d["Adj Close"].pct_change()).abs().shift(1)
    lv = np.log(d.Volume)
    d["abvol"] = lv - lv.shift(1).rolling(20).mean()
    d["abvol_l1"] = d["abvol"].shift(1)
    d["abvol_m5"] = d["abvol"].shift(1).rolling(5).mean()
    d["har1"] = d["logrange"].shift(1)
    d["har5"] = d["logrange"].shift(2).rolling(4).mean()
    d["har22"] = d["logrange"].shift(6).rolling(17).mean()
    d["dir"] = np.sign(np.log(d.Close / d.Open))
    d["gapdays"] = d["Date"].diff().dt.days
    frames.append(d)
P = pd.concat(frames, ignore_index=True)

# market HAR: cross-sectional mean of log range by date
mk = P.groupby("Date")["logrange"].mean().sort_index()
mk_l1 = mk.shift(1)
mk_m5 = mk.shift(2).rolling(4).mean()
P["mkt1"] = P["Date"].map(mk_l1)
P["mkt5"] = P["Date"].map(mk_m5)

# ------------------------------------------------------------------ tweets -> windows (ET)
docs = defaultdict(list)
cnt = defaultdict(int)
for tic in sorted(P.tic.unique()):
    dates = list(P.loc[P.tic == tic, "Date"])
    opens = [dt.datetime.combine(x.date(), dt.time(9, 30), ET) for x in dates]
    closes = [dt.datetime.combine(x.date(), dt.time(16, 0), ET) for x in dates]
    tdir = SN / "tweet/preprocessed" / tic
    seen = set()
    for fn in sorted(os.listdir(tdir)):
        with open(tdir / fn) as fh:
            for line in fh:
                tw = json.loads(line)
                t = dt.datetime.strptime(tw["created_at"], "%a %b %d %H:%M:%S %z %Y").astimezone(ET)
                toks = [w for w in tw["text"] if w not in STOP]
                key = (" ".join(toks), t.date())
                if key in seen:
                    continue
                seen.add(key)
                j = bisect.bisect_right(closes, t)
                if j >= len(dates):
                    continue
                win = "session" if t >= opens[j] else "overnight"
                docs[(tic, dates[j], win)].extend(toks)
                cnt[(tic, dates[j], win)] += 1
                if win == "session" and j + 1 < len(dates):       # becomes prev_session of next day
                    cnt[(tic, dates[j + 1], "prev_session")] += 1

P["n_over"] = [cnt.get((t, d, "overnight"), 0) for t, d in zip(P.tic, P.Date)]
P["n_prev"] = [cnt.get((t, d, "prev_session"), 0) for t, d in zip(P.tic, P.Date)]
P["n_sess"] = [cnt.get((t, d, "session"), 0) for t, d in zip(P.tic, P.Date)]
P["doc_over"] = [" ".join(docs.get((t, d, "overnight"), [])) for t, d in zip(P.tic, P.Date)]
mkt_over = P.groupby("Date")["n_over"].sum()
P["mkt_over"] = P["Date"].map(mkt_over)
for c in ["n_over", "n_prev", "n_sess", "mkt_over"]:
    P["l_" + c] = np.log1p(P[c])
P["any_over"] = (P.n_over > 0).astype(float)

S = P[(P.Date >= START) & (P.Date <= END)].dropna(
    subset=["har1", "har5", "har22", "mkt1", "mkt5", "absret_prev", "abvol", "abvol_l1", "abvol_m5", "gapdays"]
).reset_index(drop=True)
tr = (S.Date <= TRAIN_END).values
va = ((S.Date > TRAIN_END) & (S.Date <= VAL_END)).values
te = (S.Date > VAL_END).values
fit = tr | va

# per-stock top-decile threshold from TRAINING data only
q90 = S[tr].groupby("tic")["range"].quantile(0.9)
S["big"] = (S["range"] >= S["tic"].map(q90)).astype(int)

# ------------------------------------------------------------------ design matrices
dummies = pd.get_dummies(S.tic, prefix="s", dtype=float)
FEATS = {
    "M0": ["har1", "har5", "har22"],
    "M1": ["har1", "har5", "har22", "mkt1", "mkt5", "gapdays", "absret_prev", "abvol_l1"],
}
FEATS["M2"] = FEATS["M1"] + ["l_n_over", "l_n_prev", "any_over", "l_mkt_over"]
FEATS["LEAK"] = FEATS["M2"] + ["l_n_sess"]


def dense(cols, mask_fit):
    X = S[cols].astype(float).values
    mu, sd = X[mask_fit].mean(0), X[mask_fit].std(0) + 1e-9
    return np.hstack([(X - mu) / sd, dummies.values])


def ridge_fit_predict(X, y, alphas=(0.1, 1, 10, 100, 1000)):
    """choose alpha on validation, refit on train+validation, predict all rows"""
    best = min(alphas, key=lambda a: np.mean((Ridge(alpha=a).fit(X[tr], y[tr]).predict(X[va]) - y[va]) ** 2))
    m = Ridge(alpha=best).fit(X[fit], y[fit])
    return m.predict(X), best


def boot_days(dates, fn, reps=2000):
    ud = np.unique(dates)
    idx = {d: np.where(dates == d)[0] for d in ud}
    out = []
    for _ in range(reps):
        pick = rng.choice(ud, len(ud), replace=True)
        rows = np.concatenate([idx[d] for d in pick])
        out.append(fn(rows))
    return np.percentile(out, [2.5, 97.5])


res = {"n_stocks": int(S.tic.nunique()), "n_rows": int(len(S)), "n_test": int(te.sum()),
       "n_test_days": int(S.loc[te, "Date"].nunique()),
       "share_rows_with_overnight_tweets": round(float((S.n_over > 0).mean()), 3),
       "test_big_rate": round(float(S.loc[te, "big"].mean()), 4)}

# TF-IDF on overnight tweets (fit vocabulary on fit rows only)
vec = TfidfVectorizer(ngram_range=(1, 2), min_df=5, max_features=30000, sublinear_tf=True)
vec.fit(S.loc[fit, "doc_over"])
T = vec.transform(S["doc_over"])

dates_te = S.loc[te, "Date"].values
for target in ["logrange", "abvol"]:
    y = S[target].values
    bench = S["tic"].map(S[tr].groupby("tic")[target].mean()).values     # per-stock training mean
    preds, alphas = {}, {}
    cols_extra = ["abvol_m5"] if target == "abvol" else []
    for name in ["M0", "M1", "M2", "LEAK"]:
        X = dense(FEATS[name] + cols_extra, fit)
        preds[name], alphas[name] = ridge_fit_predict(X, y)
    X3 = sparse.hstack([sparse.csr_matrix(dense(FEATS["M2"] + cols_extra, fit)), T]).tocsr()
    preds["M3"], alphas["M3"] = ridge_fit_predict(X3, y, alphas=(1, 10, 100, 1000, 10000))

    yt, bt = y[te], bench[te]
    sst = lambda rows: np.sum((yt[rows] - bt[rows]) ** 2)
    out = {}
    for name, p in preds.items():
        pt = p[te]
        r2 = 1 - np.sum((yt - pt) ** 2) / sst(np.arange(len(yt)))
        lo, hi = boot_days(dates_te, lambda rows: 1 - np.sum((yt[rows] - pt[rows]) ** 2) / sst(rows), reps=1000)
        out[name] = {"oos_r2": round(float(r2), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)],
                     "alpha": alphas[name]}
    # incremental R2 of news counts and text, with day-bootstrap intervals
    for a, b in [("M1", "M2"), ("M2", "M3"), ("M0", "M1"), ("M2", "LEAK")]:
        pa, pb = preds[a][te], preds[b][te]
        d = lambda rows: (np.sum((yt[rows] - pa[rows]) ** 2) - np.sum((yt[rows] - pb[rows]) ** 2)) / sst(rows)
        lo, hi = boot_days(dates_te, d, reps=1000)
        out[f"delta_{b}_minus_{a}"] = {"value": round(float(d(np.arange(len(yt)))), 4),
                                       "ci95": [round(float(lo), 4), round(float(hi), 4)]}
    # rows with overnight tweets only
    has = (S.loc[te, "n_over"] > 0).values
    for a, b in [("M1", "M2"), ("M2", "M3")]:
        pa, pb = preds[a][te][has], preds[b][te][has]
        y_, b_ = yt[has], bt[has]
        out[f"delta_{b}_minus_{a}_rows_with_tweets"] = round(
            float((np.sum((y_ - pa) ** 2) - np.sum((y_ - pb) ** 2)) / np.sum((y_ - b_) ** 2)), 4)
    res[target] = out

    if target == "logrange":
        yb = S["big"].values[te]
        auc = {}
        for name, p in preds.items():
            pt = p[te]
            lo, hi = boot_days(dates_te, lambda rows: roc_auc_score(yb[rows], pt[rows]), reps=500)
            auc[name] = {"auc": round(float(roc_auc_score(yb, pt)), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)]}
        p1, p2 = preds["M1"][te], preds["M2"][te]
        lo, hi = boot_days(dates_te, lambda rows: roc_auc_score(yb[rows], p2[rows]) - roc_auc_score(yb[rows], p1[rows]), reps=500)
        auc["delta_M2_minus_M1"] = {"value": round(float(roc_auc_score(yb, p2) - roc_auc_score(yb, p1)), 4),
                                    "ci95": [round(float(lo), 4), round(float(hi), 4)]}
        res["big_move_auc"] = auc

# ------------------------------------------------------------------ direction with the same inputs (negative control)
ydir = (S["dir"] > 0).values
dir_out = {"test_share_up": round(float(ydir[te].mean()), 4)}
for name in ["M0", "M1", "M2"]:
    X = dense(FEATS[name], fit)
    clf = LogisticRegression(C=0.1, max_iter=3000).fit(X[fit], ydir[fit])
    p = clf.predict_proba(X)[:, 1][te]
    acc = ((p > 0.5) == ydir[te]).mean()
    lo, hi = boot_days(dates_te, lambda rows: ((p[rows] > 0.5) == ydir[te][rows]).mean(), reps=1000)
    dir_out[name] = {"acc": round(float(acc), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)],
                     "auc": round(float(roc_auc_score(ydir[te], p)), 4)}
X3 = sparse.hstack([sparse.csr_matrix(dense(FEATS["M2"], fit)), T]).tocsr()
clf = LogisticRegression(C=0.1, max_iter=3000).fit(X3[fit], ydir[fit])
p = clf.predict_proba(X3)[:, 1][te]
lo, hi = boot_days(dates_te, lambda rows: ((p[rows] > 0.5) == ydir[te][rows]).mean(), reps=1000)
dir_out["M3"] = {"acc": round(float(((p > 0.5) == ydir[te]).mean()), 4), "ci95": [round(float(lo), 4), round(float(hi), 4)],
                 "auc": round(float(roc_auc_score(ydir[te], p)), 4)}
# which inputs carry the direction signal?  logistic coefficients of M1 (standardized, no dummies)
X = dense(FEATS["M1"], fit)
clf = LogisticRegression(C=0.1, max_iter=3000).fit(X[fit], ydir[fit])
dir_out["M1_coefficients"] = {c: round(float(w), 4) for c, w in zip(FEATS["M1"], clf.coef_[0][:len(FEATS["M1"])])}
# the same model scored on the validation quarter (a different period) as a stability check
clf_tr = LogisticRegression(C=0.1, max_iter=3000).fit(X[tr], ydir[tr])
dir_out["M1_val_acc_trained_on_train_only"] = round(float((clf_tr.predict(X[va]) == ydir[va]).mean()), 4)
dir_out["val_share_up"] = round(float(ydir[va].mean()), 4)
res["direction_control"] = dir_out

# simple descriptive: mean range on days with vs without overnight tweets (test period)
g = S[te].assign(has=lambda x: x.n_over > 0).groupby("has")["range"].agg(["mean", "median", "count"])
res["test_range_by_overnight_tweets"] = {str(k): {kk: round(float(v), 5) for kk, v in row.items()} for k, row in g.iterrows()}

(OUT / "bc5_stocknet_volatility.json").write_text(json.dumps(res, indent=2, default=str))
print(json.dumps(res, indent=2, default=str))
