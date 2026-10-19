"""Step 4: the MVP experiment (same design as base case BC6), on the files from steps 1-2.

    python step4_baseline_models.py --prices data/prices --news data/news_cnyes.jsonl \
        --start 2024-10-01 --train-end 2025-06-30 --val-end 2025-09-30 --end 2026-09-30 \
        [--emb data/emb_overnight.npz --pca 8 16 32 64] [--walkforward] --out results/step4.json

Target (decision time 08:45 Taipei, before the open of trading day d)
  y_tr   log of the true range ln(max(H_d, ref_prev_close) / min(L_d, ref_prev_close))
         (ref_prev_close = exchange reference price on ex-dividend / split days, see step 1)
  big    true range in the top 10% of that stock's own fit-period values
  y_abv  log volume minus the mean log volume of the previous 20 trading days
  dir    sign of open-to-close return (negative control)
Nested ridge models (alpha chosen on the validation period, refit on train+validation)
  M0 HAR(1, 5, 22) | M1 + market, calendar, US overnight | M2 + news counts | M3 + event-type flags
  [ME_k + PCA(k) of the overnight-news embedding, if --emb is given]
95% intervals: bootstrap over test DAYS.
--walkforward adds the BC6 main table: monthly expanding-window refits (alpha fixed at 10),
R2 against each stock's own test-period mean, and the event-day subsets (M1e = M1 + earnings
and revenue flags).
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step3_align import at  # noqa: E402

FLAGS = {"rev": r"營收", "earn": r"財報|EPS|每股純益|每股盈餘|獲利|法說|季報|年報|毛利率|營益率|淨利",
         "div": r"股利|除息|除權|配息|殖利率|填息", "analyst": r"目標價|評等|調升|調降|上修|下修|外資報告|看好|看淡",
         "react": r"漲停|跌停|大漲|大跌|勁揚|重挫|走高|走低|翻紅|翻黑|收盤|收紅|收黑|漲幅|跌幅|創高|新高|新低|領漲|領跌|"
                  r"急漲|急跌|收漲|收跌|週漲|週跌|漲逾|跌逾|攻上|站上|跌破|失守|買超|賣超",
         "corp": r"併購|收購|合併|訂單|擴產|投資|合作|設廠|建廠|增資|減資|庫藏股", "disp": r"處置|注意股|警示"}
FLAGS = {k: re.compile(v) for k, v in FLAGS.items()}
POS = re.compile(r"創新高|新高|成長|增加|優於預期|上修|調升|看好|大漲|漲停|利多|強勁|攀升|飆|旺|樂觀|突破")
NEG = re.compile(r"衰退|減少|低於預期|下修|調降|看淡|大跌|跌停|利空|疲弱|重挫|虧損|下滑|跌破|悲觀|保守|下跌")


def lag_mean(s, a, b):
    """mean of s[t-b .. t-a] (a <= b), needs at least half of the values"""
    return s.shift(a).rolling(b - a + 1, min_periods=math.ceil((b - a + 1) / 2)).mean()


def load_prices(folder, codes):
    cal = pd.read_csv(folder / "tw_trading_dates.csv")["date"].tolist()
    out = {}
    for c in codes:
        d = pd.read_csv(folder / f"tw_{c}.csv").set_index("date").reindex(cal)
        tr = np.log(np.maximum(d.high, d.ref_prev_close) / np.minimum(d.low, d.ref_prev_close))
        d["tr_raw"] = tr
        d["y_tr"] = np.log(tr.clip(lower=1e-3))
        lv = np.log(d.volume.where(d.volume > 0))
        d["y_abv"] = lv - lag_mean(lv, 1, 20)
        d["oc"] = np.log(d.close / d.open)
        d["hd"] = d.y_tr.shift(1)
        d["hw"] = lag_mean(d.y_tr, 1, 5)
        d["hm"] = lag_mean(d.y_tr, 1, 22)
        d["abv1"] = d.y_abv.shift(1)
        d["abv5"] = lag_mean(d.y_abv, 1, 5)
        out[c] = d
    return cal, out


def us_features(folder, cal):
    def load(name):
        u = pd.read_csv(folder / f"us_{name}.csv", index_col=0)
        u.index = pd.to_datetime(u.index).strftime("%Y-%m-%d")
        u = u.sort_index()
        u["ret"] = np.log(u.Close / u.Close.shift(1))
        u["rng"] = np.log(np.log(u.High / u.Low).clip(lower=1e-4))
        return u
    ix, sox, tsm = load("IDX_IXIC"), load("IDX_SOX"), load("TSM")
    rows = []
    for k in range(1, len(cal)):
        lo, hi = cal[k - 1], cal[k]
        sel = [u for u in ix.index if lo <= u < hi]           # US sessions that closed in between
        if not sel:
            rows.append({"date": hi, "usn": 0}); continue
        last = sel[-1]
        rows.append({"date": hi, "usn": len(sel), "usix": ix.loc[sel, "ret"].sum(), "ussox": sox.reindex(sel)["ret"].sum(),
                     "ustsm": tsm.reindex(sel)["ret"].sum(), "usrngix": ix.loc[last, "rng"], "usrngsox": sox["rng"].get(last, np.nan)})
    f = pd.DataFrame(rows).set_index("date")
    for c in ["usix", "ussox", "ustsm"]:
        f["abs_" + c] = f[c].abs()
    return f


def news_features(path, cal, codes):
    days = [pd.Timestamp(d).date() for d in cal]
    closes = np.array([at(d, 13, 30) for d in days])
    opens = np.array([at(d, 9, 0) for d in days])
    lates = np.array([at(d, 8, 45) for d in days])
    K = len(cal)
    cnt = {c: {k: np.zeros(K) for k in ["over", "sess", "sent", *FLAGS]} for c in codes}
    mkt = {"over": np.zeros(K), "sess": np.zeros(K)}
    seen = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            x = json.loads(line)
            if x["newsId"] in seen:
                continue
            seen.add(x["newsId"])
            t = int(x["publishAt"])
            j = int(np.searchsorted(closes, t, side="right"))
            if j >= K:
                continue
            b = "sess" if t >= opens[j] else ("late" if t >= lates[j] else "over")
            if b == "late":
                continue
            mkt[b][j] += 1
            title = x.get("title") or ""
            for c in set(map(str, x.get("stock") or [])) & set(codes):
                cnt[c][b][j] += 1
                if b == "over":
                    for k, rx in FLAGS.items():
                        cnt[c][k][j] += bool(rx.search(title))
                    cnt[c]["sent"][j] += len(POS.findall(title)) - len(NEG.findall(title))
    feats = {}
    for c in codes:
        C = cnt[c]
        f = pd.DataFrame(index=cal)
        f["l_over"] = np.log1p(C["over"]); f["any_over"] = (C["over"] > 0).astype(float)
        f["l_prev"] = np.log1p(np.r_[0, C["sess"][:-1]]); f["l_sess"] = np.log1p(C["sess"])
        f["l_mover"] = np.log1p(mkt["over"]); f["l_mprev"] = np.log1p(np.r_[0, mkt["sess"][:-1]])
        for k in FLAGS:
            f["l_" + k] = np.log1p(C[k])
        f["sent"] = C["sent"]
        feats[c] = f
    return feats


def walkforward(D, specs, test_start, rng, reps, alpha=10.0):
    """monthly expanding-window refits over the test period (dates > test_start)"""
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
    te = ~np.isnan(pred["M1"])
    dates = D.date.values[te]; ud = np.unique(dates); rows_of = {d: np.where(dates == d)[0] for d in ud}
    yt = y[te]; bench = D[te].groupby("code")["y_tr"].transform("mean").values    # each stock's own test mean
    P = {n: p[te] for n, p in pred.items()}

    def r2(p, r): return 1 - np.sum((yt[r] - p[r]) ** 2) / np.sum((yt[r] - bench[r]) ** 2)

    def ci(fn):
        v = [fn(np.concatenate([rows_of[d] for d in rng.choice(ud, len(ud))])) for _ in range(reps)]
        return [round(float(x), 4) for x in np.percentile(v, [2.5, 97.5])]

    allr = np.arange(len(yt))
    out = {n: {"r2_within": round(float(r2(p, allr)), 4), "ci95": ci(lambda r, p=p: r2(p, r))} for n, p in P.items()}
    for a_, b_ in [("M0", "M1"), ("M1", "M2"), ("M2", "M3"), ("M1", "M1e")]:
        f = lambda r, pa=P[a_], pb=P[b_]: r2(pb, r) - r2(pa, r)
        out[f"delta_{b_}_minus_{a_}"] = {"value": round(float(f(allr)), 4), "ci95": ci(f)}
    sub = D[te]
    groups = {"earnings_or_revenue_news": ((sub.l_earn > 0) | (sub.l_rev > 0)).values,
              "other_news": ((sub.any_over > 0) & ~((sub.l_earn > 0) | (sub.l_rev > 0))).values,
              "no_news": (sub.any_over == 0).values}
    for g, mask in groups.items():
        idx = np.where(mask)[0]
        if len(idx) < 20:
            continue
        o = {"n": int(len(idx))}
        for n in ["M1", "M1e"]:
            res_ = yt[idx] - P[n][idx]
            o[n] = {"under_prediction_pct": round(float(100 * (np.exp(res_.mean()) - 1)), 1),
                    "r2_within": round(float(r2(P[n], idx)), 4)}
        out["subset_" + g] = o
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="data/prices"); ap.add_argument("--news", default="data/news_cnyes.jsonl")
    ap.add_argument("--start", default="2024-10-01"); ap.add_argument("--train-end", default="2025-06-30")
    ap.add_argument("--val-end", default="2025-09-30"); ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--codes", nargs="*", default=None)
    ap.add_argument("--emb", default=None, help="npz with keys code, date, vec (overnight-news mean embedding)")
    ap.add_argument("--pca", nargs="*", type=int, default=[8, 16, 32, 64])
    ap.add_argument("--out", default="results/step4.json"); ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--walkforward", action="store_true")
    ap.add_argument("--universe", choices=["mega", "mid"], default=None,
                    help="use the MEGA or MID list from step1_prices.py instead of --codes")
    a = ap.parse_args()
    folder = Path(a.prices)
    if a.universe:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from step1_prices import MEGA, MID
        a.codes = MEGA if a.universe == "mega" else MID
    codes = a.codes or sorted(p.stem[3:] for p in folder.glob("tw_*.csv") if p.stem[3:].isdigit())
    missing = [c for c in codes if not (folder / f"tw_{c}.csv").exists()]
    if missing:
        print("no price file, skipped:", " ".join(missing))
    codes = [c for c in codes if c not in missing]
    cal, px = load_prices(folder, codes)
    us = us_features(folder, cal)
    nf = news_features(a.news, cal, codes)
    idx_d = pd.read_csv(folder / "tw_trading_dates.csv")["date"]
    gapdays = pd.Series(pd.to_datetime(idx_d).diff().dt.days.values, index=cal)

    # market HAR from the cross-sectional mean of the stocks' log true range (no index file needed)
    mk = pd.concat([px[c].y_tr for c in codes], axis=1).mean(axis=1)
    frames = []
    for i, c in enumerate(codes):
        d = px[c].join(us).join(nf[c])
        d["mk1"] = mk.shift(1); d["mk5"] = lag_mean(mk, 1, 5); d["gapdays"] = gapdays
        d["code"] = c; d["ci"] = i
        frames.append(d.reset_index().rename(columns={"index": "date"}))
    D = pd.concat(frames, ignore_index=True)
    D = D[(D.date >= a.start) & (D.date <= a.end)]
    F0 = ["hd", "hw", "hm"]
    F1 = F0 + ["mk1", "mk5", "gapdays", "abv1", "abs_usix", "abs_ussox", "usrngix", "usrngsox", "abs_ustsm", "usn"]
    F2 = F1 + ["l_over", "any_over", "l_prev", "l_mover", "l_mprev"]
    F3 = F2 + ["l_" + k for k in FLAGS]
    D = D.dropna(subset=F3 + ["y_tr", "y_abv", "tr_raw", "abv5"]).reset_index(drop=True)
    D = D[~D.is_event_day.astype(bool)].reset_index(drop=True)     # ex-dividend / split days
    tr = (D.date <= a.train_end).values; va = ((D.date > a.train_end) & (D.date <= a.val_end)).values
    fit = tr | va; te = (D.date > a.val_end).values
    dummies = pd.get_dummies(D.code, dtype=float).values
    rng = np.random.default_rng(0)

    def design(cols, extra=None):
        X = D[cols].astype(float).values
        mu, sd = X[fit].mean(0), X[fit].std(0) + 1e-9
        parts = [(X - mu) / sd, dummies]
        if extra is not None:
            parts.insert(1, extra)
        return np.hstack(parts)

    def fit_predict(X, y):
        best = min([0.1, 1, 10, 100, 1000, 10000],
                   key=lambda al: np.mean((Ridge(alpha=al).fit(X[tr], y[tr]).predict(X[va]) - y[va]) ** 2))
        return Ridge(alpha=best).fit(X[fit], y[fit]).predict(X), best

    test_days = D.loc[te, "date"].values
    ud = np.unique(test_days); rows_of = {d: np.where(test_days == d)[0] for d in ud}

    def boot(fn, reps):
        vals = []
        for _ in range(reps):
            r = np.concatenate([rows_of[d] for d in rng.choice(ud, len(ud))])
            vals.append(fn(r))
        return [round(float(v), 4) for v in np.percentile(vals, [2.5, 97.5])]

    res = {"n_rows": int(len(D)), "n_test": int(te.sum()), "n_test_days": int(len(ud)), "codes": codes}
    emb = None
    if a.emb:
        z = np.load(a.emb, allow_pickle=True)
        key = {(c, d): v for c, d, v in zip(z["code"], z["date"], z["vec"])}
        dim = z["vec"].shape[1]
        emb = np.vstack([key.get((c, d), np.zeros(dim)) for c, d in zip(D.code, D.date)])

    for target in ["y_tr", "y_abv"]:
        y = D[target].values
        bench = D.code.map(D[fit].groupby("code")[target].mean()).values
        extra = ["abv5"] if target == "y_abv" else []
        specs = {"M0": F0, "M1": F1, "M2": F2, "M3": F3, "LEAK": F2 + ["l_sess"]}
        P = {n: fit_predict(design(c + extra), y) for n, c in specs.items()}
        if emb is not None:
            from sklearn.decomposition import PCA
            for k in a.pca:
                pcs = PCA(n_components=k).fit(emb[fit]).transform(emb)
                pcs = (pcs - pcs[fit].mean(0)) / (pcs[fit].std(0) + 1e-9)
                P[f"ME{k}"] = fit_predict(design(F3 + extra, pcs), y)
        yt, bt = y[te], bench[te]
        out = {}
        for n, (p, al) in P.items():
            pt = p[te]
            f = lambda r, pt=pt: 1 - np.sum((yt[r] - pt[r]) ** 2) / np.sum((yt[r] - bt[r]) ** 2)
            out[n] = {"r2": round(float(f(np.arange(len(yt)))), 4), "ci95": boot(f, a.reps // 2), "alpha": al}
        for x, z_ in [("M0", "M1"), ("M1", "M2"), ("M2", "M3"), ("M1", "M3")] + [("M3", m) for m in P if m.startswith("ME")]:
            pa, pb = P[x][0][te], P[z_][0][te]
            f = lambda r, pa=pa, pb=pb: (np.sum((yt[r] - pa[r]) ** 2) - np.sum((yt[r] - pb[r]) ** 2)) / np.sum((yt[r] - bt[r]) ** 2)
            out[f"delta_{z_}_minus_{x}"] = {"value": round(float(f(np.arange(len(yt)))), 4), "ci95": boot(f, a.reps)}
        if target == "y_tr":
            q90 = D[fit].groupby("code")["tr_raw"].quantile(0.9)
            lab = (D.tr_raw >= D.code.map(q90)).values[te]
            out["big_move_auc"] = {n: round(float(roc_auc_score(lab, p[te])), 4) for n, (p, _) in P.items()}
            out["big_move_rate_test"] = round(float(lab.mean()), 4)
        res[target] = out

    # negative control: direction of the open-to-close return
    ydir = np.where(D.oc.values > 0, 1.0, -1.0)
    p, _ = fit_predict(design(F3 + ["usix", "ussox", "ustsm", "sent"]), ydir)
    keep = te & (D.oc.values != 0)
    acc = float((np.sign(p[keep]) == ydir[keep]).mean())
    res["direction_control"] = {"acc": round(acc, 4), "test_share_up": round(float((ydir[keep] > 0).mean()), 4)}
    if a.walkforward:
        res["walkforward"] = walkforward(D, {"M0": F0, "M1": F1, "M2": F2, "M3": F3,
                                             "M1e": F1 + ["l_earn", "l_rev"]}, a.val_end, rng, a.reps)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
