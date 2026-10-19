"""BC2: synthetic market showing how news alignment and data splitting can fake predictability.

Part 1  information timing.  Same simulated market, four ways of lining up news with returns.
Part 2  splitting.  News "stories" last several days and carry a story-specific drift; random
        K-fold puts days of the same story on both sides of the split.

All quantities are in units of the daily idiosyncratic volatility; only directions matter here.
The true, generalisable news effect is deliberately tiny.  Numbers illustrate patterns only.

Usage:  python3 -I bc2_synthetic_leakage.py <results_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold
from sklearn.neighbors import KNeighborsClassifier

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(7)
res = {}

# ------------------------------------------------------------------ Part 1: timing
M, T = 30, 1500                       # stocks, trading days (about 6 years)
f_gap = rng.normal(0, 0.6, T)         # overnight market move (e.g. driven by the US session)
f_day = rng.normal(0, 0.8, T)         # intraday market move
us_overnight = 0.7 * f_gap / 0.6 + np.sqrt(1 - 0.49) * rng.normal(0, 1, T)  # corr 0.7 with f_gap

has_on = rng.random((T, M)) < 0.30    # after-close announcement that hits the next open
s_on = np.where(has_on, rng.normal(0, 1, (T, M)), 0.0)
has_pre = rng.random((T, M)) < 0.40   # morning news with a tiny genuine effect on the session
s_pre = np.where(has_pre, rng.normal(0, 1, (T, M)), 0.0)

gap = f_gap[:, None] + 0.8 * s_on + rng.normal(0, 0.5, (T, M))
oc = f_day[:, None] + 0.05 * s_pre + rng.standard_t(4, (T, M)) / np.sqrt(2)
cc = gap + oc

# Evening "reaction" stories describing what the stock did today (published after the close)
has_react = rng.random((T, M)) < 0.60
s_react = np.where(has_react, cc / cc.std() + rng.normal(0, 0.7, (T, M)), 0.0)

# Information sets.  Index t = the trading day whose return we want to predict.
prev = lambda a: np.vstack([np.zeros((1, a.shape[1])), a[:-1]])  # value from day t-1
us = np.repeat(us_overnight[:, None], M, axis=1)

before_open = [s_pre, prev(s_react), prev(s_on), us]   # all of this is public before 09:00 on day t
feature_sets = {
    # naive: every item stamped with calendar day t, including tonight's stories about today
    "naive_calendar_day__cc": ([s_pre, s_react, s_on, us], cc),
    # only what is public before today's open, but scored on close(t-1) -> close(t)
    "known_before_open__cc": (before_open, cc),
    # same information, scored on the return still tradable after seeing it: open(t) -> close(t)
    "known_before_open__oc": (before_open, oc),
    # what is public at yesterday's close (yesterday's morning news + yesterday's return),
    # scored on close(t-1) -> close(t), i.e. a trade entered at yesterday's close
    "known_at_prev_close__cc": ([prev(s_pre), prev(cc)], cc),
}

split = int(T * 0.6)
part1 = {}
for name, (feats, y) in feature_sets.items():
    X = np.stack([f for f in feats], axis=-1)            # (T, M, k)
    Xtr, ytr = X[:split].reshape(-1, X.shape[-1]), (y[:split] > 0).ravel()
    Xte, yte = X[split:].reshape(-1, X.shape[-1]), (y[split:] > 0).ravel()
    clf = LogisticRegression(C=1.0, max_iter=1000).fit(Xtr, ytr)
    acc = (clf.predict(Xte) == yte).mean()
    # day-clustered standard error of accuracy
    correct = (clf.predict(Xte) == yte).reshape(-1, M).mean(axis=1)
    se = correct.std(ddof=1) / np.sqrt(len(correct))
    part1[name] = {"test_accuracy": round(float(acc), 4), "day_clustered_se": round(float(se), 4),
                   "test_days": int(T - split), "test_predictions": int(yte.size)}
res["part1_timing"] = part1

# ------------------------------------------------------------------ Part 2: splitting
D, M2, T2 = 32, 30, 1500
w = rng.normal(0, 1, D); w /= np.linalg.norm(w)        # direction that encodes real sentiment
rows = []
for i in range(M2):
    t = 0
    while t < T2:
        L = rng.geometric(1 / 6)                       # story length, mean 6 days
        centre = rng.normal(0, 1, D)
        drift = rng.normal(0, 0.35)                    # story-specific drift, not knowable in advance
        for tt in range(t, min(t + L, T2)):
            if rng.random() < 0.7:                     # a news day for this stock
                s = rng.normal(0, 1)                   # article sentiment (generalisable part)
                x = centre + 0.6 * s * w + rng.normal(0, 0.5, D)
                r = drift + 0.05 * s + rng.standard_t(4) / np.sqrt(2)
                rows.append((tt, i, x, r > 0))
        t += L
days = np.array([r[0] for r in rows])
X2 = np.stack([r[2] for r in rows])
y2 = np.array([r[3] for r in rows])
order = np.argsort(days, kind="stable")
days, X2, y2 = days[order], X2[order], y2[order]

models = {"logistic": lambda: LogisticRegression(C=1.0, max_iter=2000),
          "knn15": lambda: KNeighborsClassifier(n_neighbors=15)}


def random_kfold(make):
    accs = []
    for tr, te in KFold(5, shuffle=True, random_state=0).split(X2):
        accs.append((make().fit(X2[tr], y2[tr]).predict(X2[te]) == y2[te]).mean())
    return float(np.mean(accs))


def blocked_kfold(make, embargo=0):
    """Contiguous time blocks; optionally drop training rows within `embargo` days of the test block."""
    accs = []
    edges = np.linspace(0, T2, 6).astype(int)
    for a, b in zip(edges[:-1], edges[1:]):
        te = (days >= a) & (days < b)
        tr = ~te & ((days < a - embargo) | (days >= b + embargo))
        accs.append((make().fit(X2[tr], y2[tr]).predict(X2[te]) == y2[te]).mean())
    return float(np.mean(accs))


def walk_forward(make, n_steps=5, start=0.5):
    accs = []
    cuts = np.linspace(int(T2 * start), T2, n_steps + 1).astype(int)
    for a, b in zip(cuts[:-1], cuts[1:]):
        tr, te = days < a, (days >= a) & (days < b)
        accs.append((make().fit(X2[tr], y2[tr]).predict(X2[te]) == y2[te]).mean())
    return float(np.mean(accs))


part2 = {"n_samples": int(len(y2)), "share_up": round(float(y2.mean()), 4)}
for name, make in models.items():
    part2[name] = {
        "random_5fold": round(random_kfold(make), 4),
        "blocked_5fold_no_embargo": round(blocked_kfold(make, 0), 4),
        "blocked_5fold_embargo20": round(blocked_kfold(make, 20), 4),
        "walk_forward": round(walk_forward(make), 4),
    }
# Ceiling for a model that only uses the generalisable sentiment (known s, true sign rule)
s_proj = X2 @ w
part2["oracle_sentiment_only_accuracy"] = round(float(((s_proj > 0) == y2).mean()), 4)
res["part2_splitting"] = part2

(OUT / "bc2_synthetic_leakage.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
