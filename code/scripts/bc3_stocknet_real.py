"""BC3: real-data base case on StockNet (Xu & Cohen, ACL 2018): tweets + daily prices,
85 usable US stocks (3 of 88 dropped for data problems), 2014-01-01 .. 2015-12-31.

What it measures
  E1  base rates and simple baselines on a time-ordered test half-year (2015-07 .. 2015-12)
  E2  which tweets "predict" which return: tweets from three time windows x three return targets
  E3  random split vs time-ordered split for the same model
  E4  naive vs day-clustered confidence intervals; cross-sectional correlation of returns

Text representations
  tfidf  : word 1-2 gram TF-IDF -> L2 logistic regression
  wvec   : mean of spaCy en_core_web_md static word vectors (300-d) -> L2 logistic regression
           (a stand-in for "embeddings"; a real project would use a sentence-embedding model)

Usage:  python3 -I bc3_stocknet_real.py <stocknet_dir> <results_dir>
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
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import matthews_corrcoef
from sklearn.preprocessing import StandardScaler

SN = Path(sys.argv[1])
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "results")
OUT.mkdir(parents=True, exist_ok=True)
ET = ZoneInfo("America/New_York")
rng = np.random.default_rng(42)
START, END = pd.Timestamp("2014-01-02"), pd.Timestamp("2015-12-31")
TRAIN_END, VAL_END = pd.Timestamp("2015-03-31"), pd.Timestamp("2015-06-30")
DROP = {"AGFS", "GMRE", "SPLP"}  # too few rows or many Open==Close rows (illiquid / bad quotes)

# ------------------------------------------------------------------ prices
px = {}
for f in sorted((SN / "price/raw").glob("*.csv")):
    tic = f.stem
    if tic in DROP or not (SN / "tweet/preprocessed" / tic).exists():
        continue
    d = pd.read_csv(f, parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)
    adj = d["Adj Close"] / d["Close"]
    d["r_cc"] = d["Adj Close"].pct_change()
    d["r_oc"] = d["Close"] / d["Open"] - 1
    d["r_gap"] = (d["Open"] * adj) / d["Adj Close"].shift(1) - 1
    for k in range(1, 6):
        d[f"lag{k}"] = d["r_cc"].shift(k)
    px[tic] = d
tickers = sorted(px)

# equal-weighted market return and its lags (for the price-only baseline)
mkt = pd.concat([px[t].set_index("Date")["r_cc"].rename(t) for t in tickers], axis=1)
mkt_ret = mkt.mean(axis=1)
mlag = {k: mkt_ret.shift(k) for k in (1, 2)}

# ------------------------------------------------------------------ tweets -> windows
def session_bounds(dates):
    opens = [dt.datetime.combine(x.date(), dt.time(9, 30), ET) for x in dates]
    closes = [dt.datetime.combine(x.date(), dt.time(16, 0), ET) for x in dates]
    return opens, closes

docs = defaultdict(list)     # (tic, date, window) -> tokens
n_tweets = defaultdict(int)
STOP = {"AT_USER", "URL", "rt", "$", "-", ":", ".", ",", "!", "?", "#"}
for tic in tickers:
    dates = list(px[tic]["Date"])
    opens, closes = session_bounds(dates)
    tdir = SN / "tweet/preprocessed" / tic
    seen = set()
    for fn in sorted(os.listdir(tdir)):
        with open(tdir / fn) as fh:
            for line in fh:
                tw = json.loads(line)
                t = dt.datetime.strptime(tw["created_at"], "%a %b %d %H:%M:%S %z %Y").astimezone(ET)
                toks = [w for w in tw["text"] if w not in STOP]
                key = (" ".join(toks), t.date())
                if key in seen:          # drop exact duplicates (retweets) within a calendar day
                    continue
                seen.add(key)
                j = bisect.bisect_right(closes, t)   # first session whose close is after t
                if j >= len(dates):
                    continue
                win = "session" if t >= opens[j] else "overnight"
                day = dates[j]
                docs[(tic, day, win)].extend(toks)
                n_tweets[(tic, day, win)] += 1

# ------------------------------------------------------------------ sample table
rows = []
for tic in tickers:
    d = px[tic]
    dates = list(d["Date"])
    for i in range(1, len(d)):
        day = dates[i]
        if day < START or day > END:
            continue
        prev_day = dates[i - 1]
        r = d.iloc[i]
        if not np.isfinite([r.r_cc, r.r_oc, r.r_gap]).all():
            continue
        rows.append({
            "tic": tic, "date": day,
            "r_cc": r.r_cc, "r_oc": r.r_oc, "r_gap": r.r_gap,
            **{f"lag{k}": r[f"lag{k}"] for k in range(1, 6)},
            **{f"mlag{k}": mlag[k].get(day, np.nan) for k in range(1, 3)},
            "doc_prev_session": " ".join(docs.get((tic, prev_day, "session"), [])),
            "doc_overnight": " ".join(docs.get((tic, day, "overnight"), [])),
            "doc_session": " ".join(docs.get((tic, day, "session"), [])),
            "n_prev_session": n_tweets.get((tic, prev_day, "session"), 0),
            "n_overnight": n_tweets.get((tic, day, "overnight"), 0),
            "n_session": n_tweets.get((tic, day, "session"), 0),
        })
S = pd.DataFrame(rows).dropna(subset=[f"lag{k}" for k in range(1, 6)] + ["mlag1", "mlag2"])
S = S[(S.r_cc != 0) & (S.r_oc != 0) & (S.r_gap != 0)].reset_index(drop=True)
tr = S.date <= TRAIN_END
va = (S.date > TRAIN_END) & (S.date <= VAL_END)
te = S.date > VAL_END
trva = tr | va

# ------------------------------------------------------------------ helpers
def day_cluster_ci(correct, dates, reps=2000):
    df = pd.DataFrame({"c": correct, "d": dates.values})
    g = df.groupby("d")["c"].agg(["sum", "count"])
    s, c = g["sum"].values, g["count"].values
    idx = rng.integers(0, len(g), (reps, len(g)))
    boot = s[idx].sum(1) / c[idx].sum(1)
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def summarize(pred, y, dates):
    correct = (pred == y).astype(float)
    acc = correct.mean()
    n = len(correct)
    naive = 1.96 * np.sqrt(acc * (1 - acc) / n)
    lo, hi = day_cluster_ci(correct, dates)
    return {"acc": round(acc, 4), "mcc": round(float(matthews_corrcoef(y, pred)), 4),
            "n": int(n), "naive_95ci": [round(acc - naive, 4), round(acc + naive, 4)],
            "day_clustered_95ci": [round(lo, 4), round(hi, 4)]}


wv_cache = {}
W_CACHE = {}
try:
    import spacy
    NLP = spacy.load("en_core_web_md")
    VEC = NLP.vocab.vectors
except Exception:  # spaCy model not installed
    NLP = None


def wvec(doc):
    toks = doc.split()
    vs = []
    for w in toks:
        if w not in wv_cache:
            key = NLP.vocab.strings[w] if w in NLP.vocab.strings else None
            wv_cache[w] = VEC[key] if (key is not None and key in VEC) else None
        if wv_cache[w] is not None:
            vs.append(wv_cache[w])
    return np.mean(vs, axis=0) if vs else np.zeros(VEC.shape[1], dtype=np.float32)


def fit_text(rep, col, ycol, train_mask, val_mask, test_mask):
    """Choose C on val, refit on train+val, return predictions on test."""
    Cs = [0.01, 0.03, 0.1, 0.3, 1.0, 3.0]
    y = (S[ycol] > 0).values
    if rep == "tfidf":
        def feats(fit_mask, *apply_masks):
            v = TfidfVectorizer(ngram_range=(1, 2), min_df=5, max_features=50000, sublinear_tf=True)
            Xf = v.fit_transform(S.loc[fit_mask, col])
            return [Xf] + [v.transform(S.loc[m, col]) for m in apply_masks]
    else:
        if col not in W_CACHE:
            W_CACHE[col] = np.vstack([wvec(x) for x in S[col]])
        W = W_CACHE[col]
        def feats(fit_mask, *apply_masks):
            sc = StandardScaler().fit(W[fit_mask.values])
            return [sc.transform(W[fit_mask.values])] + [sc.transform(W[m.values]) for m in apply_masks]
    Xtr, Xva = feats(train_mask, val_mask)
    best = max(Cs, key=lambda C: (LogisticRegression(C=C, max_iter=3000).fit(Xtr, y[train_mask.values])
                                   .predict(Xva) == y[val_mask.values]).mean())
    fit_mask = train_mask | val_mask
    Xfit, Xte = feats(fit_mask, test_mask)
    clf = LogisticRegression(C=best, max_iter=3000).fit(Xfit, y[fit_mask.values])
    return clf.predict(Xte), best


res = {"n_stocks": len(tickers), "n_samples": int(len(S)),
       "periods": {"train": "2014-01..2015-03", "val": "2015-04..2015-06", "test": "2015-07..2015-12"},
       "n_test": int(te.sum()), "n_test_days": int(S.loc[te, "date"].nunique())}

# ------------------------------------------------------------------ E1 base rates & baselines
yte_cc = (S.loc[te, "r_cc"] > 0).values
res["E1"] = {
    "share_up_cc_train": round(float((S.loc[trva, "r_cc"] > 0).mean()), 4),
    "share_up_cc_test": round(float(yte_cc.mean()), 4),
    "share_up_oc_test": round(float((S.loc[te, "r_oc"] > 0).mean()), 4),
    "share_up_gap_test": round(float((S.loc[te, "r_gap"] > 0).mean()), 4),
    "coverage_share_with_tweets": {w: round(float((S[f"n_{w}"] > 0).mean()), 3)
                                   for w in ["prev_session", "overnight", "session"]},
    "median_tweets_when_present": {w: float(S.loc[S[f"n_{w}"] > 0, f"n_{w}"].median())
                                   for w in ["prev_session", "overnight", "session"]},
}
maj = (S.loc[trva, "r_cc"] > 0).mean() > 0.5
base = {"majority_from_train": summarize(np.full(te.sum(), maj), yte_cc, S.loc[te, "date"]),
        "momentum_prev_sign": summarize((S.loc[te, "lag1"] > 0).values, yte_cc, S.loc[te, "date"]),
        "reversal_prev_sign": summarize((S.loc[te, "lag1"] <= 0).values, yte_cc, S.loc[te, "date"])}
pcols = [f"lag{k}" for k in range(1, 6)] + ["mlag1", "mlag2"]
sc = StandardScaler().fit(S.loc[trva, pcols])
lr = LogisticRegression(C=1.0, max_iter=2000).fit(sc.transform(S.loc[trva, pcols]), (S.loc[trva, "r_cc"] > 0))
base["price_only_logistic"] = summarize(lr.predict(sc.transform(S.loc[te, pcols])), yte_cc, S.loc[te, "date"])
res["E1"]["baselines_cc"] = base

# ------------------------------------------------------------------ E2 window x target
E2 = {}
for rep in ["tfidf"] + (["wvec"] if NLP else []):
    for win in ["prev_session", "overnight", "session"]:
        for tgt in ["r_cc", "r_oc", "r_gap"]:
            pred, C = fit_text(rep, f"doc_{win}", tgt, tr, va, te)
            yv = (S.loc[te, tgt] > 0).values
            out = summarize(pred, yv, S.loc[te, "date"])
            out["C"] = C
            out["test_share_up"] = round(float(yv.mean()), 4)
            has = (S.loc[te, f"n_{win}"] > 0).values          # rows that actually have tweets
            out["subset_with_tweets"] = summarize(pred[has], yv[has], S.loc[te, "date"][has])
            if tgt == "r_cc":                                   # StockNet-style: drop small moves
                big = ((S.loc[te, "r_cc"] <= -0.005) | (S.loc[te, "r_cc"] > 0.0055)).values
                out["subset_big_moves_stocknet_rule"] = summarize(pred[big], yv[big], S.loc[te, "date"][big])
            E2[f"{rep}|{win}|{tgt}"] = out
res["E2"] = E2

# ------------------------------------------------------------------ E5 a transparent lexicon score
# A short hand-made word list (not a validated dictionary): does the tone of tweets in each window
# line up with the return of each period?  Contemporaneous windows describe moves already made.
POS = set("up bull bullish long buy buying call calls green gain gains rally beat beats higher surge "
          "soar soars jump jumps breakout upgrade upgraded rise rises rising strong record high highs".split())
NEG = set("down bear bearish short sell selling put puts red loss losses drop drops miss misses lower "
          "plunge plunges fall falls falling downgrade downgraded weak low lows crash dump tank tanks slump".split())


def tone(doc):
    toks = doc.split()
    p = sum(t in POS for t in toks)
    n = sum(t in NEG for t in toks)
    return (p - n) / (p + n) if p + n else 0.0


from scipy.stats import spearmanr  # noqa: E402

E5 = {}
for win in ["prev_session", "overnight", "session"]:
    sc_ = S[f"doc_{win}"].map(tone)
    keep = (S[f"n_{win}"] >= 2) & (sc_ != 0)
    for tgt in ["r_cc", "r_oc", "r_gap"]:
        rho = spearmanr(sc_[keep], S.loc[keep, tgt]).correlation
        hit = ((sc_[keep] > 0) == (S.loc[keep, tgt] > 0)).astype(float)
        lo, hi = day_cluster_ci(hit.values, S.loc[keep, "date"])
        E5[f"{win}|{tgt}"] = {"n": int(keep.sum()), "spearman": round(float(rho), 4),
                              "hit_rate": round(float(hit.mean()), 4),
                              "day_clustered_95ci": [round(lo, 4), round(hi, 4)]}
# yesterday's return vs tweets in yesterday's session (the reaction we expect)
keep = (S["n_prev_session"] >= 2)
sc_prev = S["doc_prev_session"].map(tone)
keep = keep & (sc_prev != 0)
E5["prev_session|lag1 (yesterday's own return)"] = {
    "n": int(keep.sum()),
    "spearman": round(float(spearmanr(sc_prev[keep], S.loc[keep, "lag1"]).correlation), 4),
    "hit_rate": round(float(((sc_prev[keep] > 0) == (S.loc[keep, "lag1"] > 0)).mean()), 4)}
res["E5"] = E5

# ------------------------------------------------------------------ E3 random vs time split
perm = rng.permutation(len(S))
n80 = int(0.8 * len(S))
r_tr = np.zeros(len(S), bool); r_tr[perm[: int(0.65 * len(S))]] = True
r_va = np.zeros(len(S), bool); r_va[perm[int(0.65 * len(S)): n80]] = True
r_te = np.zeros(len(S), bool); r_te[perm[n80:]] = True
E3 = {}
for rep in ["tfidf"] + (["wvec"] if NLP else []):
    for win, tgt in [("overnight", "r_cc"), ("prev_session", "r_cc"), ("session", "r_cc")]:
        pred, C = fit_text(rep, f"doc_{win}", tgt, pd.Series(r_tr), pd.Series(r_va), pd.Series(r_te))
        yv = (S.loc[r_te, tgt] > 0).values
        E3[f"{rep}|{win}|{tgt}|random_split"] = summarize(pred, yv, S.loc[r_te, "date"])
        E3[f"{rep}|{win}|{tgt}|time_split"] = E2[f"{rep}|{win}|{tgt}"]
res["E3"] = E3

# E3b: random split by DAY (all stocks of a day on the same side).  If the inflation in E3 comes
# from other stocks of the same day sitting in the training set, it should disappear here.
udays = S["date"].drop_duplicates().sample(frac=1.0, random_state=1).values
cut1, cut2 = int(0.65 * len(udays)), int(0.8 * len(udays))
g_tr = S["date"].isin(udays[:cut1]); g_va = S["date"].isin(udays[cut1:cut2]); g_te = S["date"].isin(udays[cut2:])
E3b = {}
for win in ["overnight", "prev_session", "session"]:
    pred, C = fit_text("tfidf", f"doc_{win}", "r_cc", g_tr, g_va, g_te)
    yv = (S.loc[g_te, "r_cc"] > 0).values
    E3b[f"tfidf|{win}|r_cc|random_days_split"] = summarize(pred, yv, S.loc[g_te, "date"])
res["E3b"] = E3b

# ------------------------------------------------------------------ E4 cross-sectional dependence
R = mkt.loc[(mkt.index >= START) & (mkt.index <= END), tickers].dropna(axis=1, thresh=400)
C = R.corr().values
iu = np.triu_indices_from(C, 1)
U = (R > 0).astype(float).where(R.notna())
CU = U.corr().values
res["E4"] = {"mean_pairwise_corr_returns": round(float(np.nanmean(C[iu])), 3),
             "mean_pairwise_corr_up_indicator": round(float(np.nanmean(CU[iu])), 3),
             "stocks_used": int(R.shape[1])}

(OUT / "bc3_stocknet_real.json").write_text(json.dumps(res, indent=2, default=str))
print(json.dumps(res, indent=2, default=str))
