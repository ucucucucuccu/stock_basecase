"""Put the BC6 numbers (browser run, results/bc6_taiwan.json) next to the Python reproduction
(step4_{mid,mega}.json and step4_supplement_{mid,mega}.json), item by item as in report section 7.1.

    python bc6_comparison.py original_results/bc6_taiwan.json results results/bc6_vs_step4.csv
"""
import csv
import json
import sys
from pathlib import Path

bc6 = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
res = Path(sys.argv[2])
rows = []


def add(section, item, group, orig, repro, note=""):
    d = None if orig is None or repro is None else round(repro - orig, 4)
    rows.append({"section": section, "item": item, "group": group, "BC6": orig, "reproduced": repro, "diff": d, "note": note})


def ci(x):
    return "" if x is None else f"[{x[0]:.3f}, {x[1]:.3f}]"


for g, key in [("mega (權值股)", "U1"), ("mid (中覆蓋組)", "U2")]:
    u = "mega" if key == "U1" else "mid"
    s4 = json.loads((res / f"step4_{u}.json").read_text(encoding="utf-8"))
    sp = json.loads((res / f"step4_supplement_{u}.json").read_text(encoding="utf-8"))
    B, W, E, F = bc6[key], s4["walkforward"], bc6[key]["event_subsets"], bc6[key]["fixed_split"]
    bw = B["walkforward_within"]
    # sample size
    add("n", "rows (fixed split)", g, F["n"]["rows"], s4["n_rows"])
    add("n", "test rows", g, F["n"]["test"], s4["n_test"])
    add("n", "test days", g, F["n"]["testDays"], s4["n_test_days"])
    # A
    for m in ["M0", "M1", "M2", "M3"]:
        add("A walk-forward R2", m, g, bw[m]["r2"], W[m]["r2_within"], f"CI BC6 {ci(bw[m]['ci'])} / repro {ci(W[m]['ci95'])}")
    for a_, b_ in [("M0", "M1"), ("M1", "M2"), ("M2", "M3")]:
        o, r = bw[f"d_{b_}_{a_}"], W[f"delta_{b_}_minus_{a_}"]
        add("A walk-forward dR2", f"{b_}-{a_}", g, o["v"], r["value"], f"CI BC6 {ci(o['ci'])} / repro {ci(r['ci95'])}")
    add("A walk-forward dR2", "M3-M1", g, bw["d_M3_M1"]["v"], round(W["M3"]["r2_within"] - W["M1"]["r2_within"], 4),
        f"CI BC6 {ci(bw['d_M3_M1']['ci'])} / repro: point only")
    # B
    for bk, rk in [("earnRev", "earnings_or_revenue_news"), ("otherNews", "other_news"), ("noNews", "no_news")]:
        o, r, sup = E[bk], W[f"subset_{rk}"], sp["walkforward_alpha10"][rk]
        add("B event subsets", f"{rk}: n", g, o["n"], r["n"])
        add("B event subsets", f"{rk}: M1 under-prediction %", g, o["M1"]["excessPct"], r["M1"]["under_prediction_pct"])
        add("B event subsets", f"{rk}: M1 R2", g, o["M1"]["r2within"], r["M1"]["r2_within"])
        add("B event subsets", f"{rk}: M1e under-prediction %", g, o["M1e"]["excessPct"], r["M1e"]["under_prediction_pct"])
        add("B event subsets", f"{rk}: M1e R2", g, o["M1e"]["r2within"], r["M1e"]["r2_within"])
        add("B event subsets", f"{rk}: dR2 M1e-M1", g, o["dR2_M1e_M1"]["v"], sup["delta_M1e_minus_M1"]["value"],
            f"CI BC6 {ci(o['dR2_M1e_M1']['ci'])} / repro {ci(sup['delta_M1e_minus_M1']['ci95'])} (supplement)")
    o, r = E["all"], W["delta_M1e_minus_M1"]
    add("B event subsets", "all: dR2 M1e-M1", g, o["dR2_M1e_M1"]["v"], r["value"], f"CI BC6 {ci(o['dR2_M1e_M1']['ci'])} / repro {ci(r['ci95'])}")
    # C
    for m in ["M0", "M1", "M2"]:
        add("C big-move AUC (fixed split)", m, g, F["y_tr"]["big"][m]["auc"], s4["y_tr"]["big_move_auc"][m])
    add("C big-move AUC (fixed split)", "test big-move rate", g, F["y_tr"]["big"]["rate_test"], s4["y_tr"]["big_move_rate_test"])
    for m in ["M0", "M1", "M2"]:
        add("C abnormal volume R2 (fixed split)", m, g, F["y_abv"][m]["r2"], s4["y_abv"][m]["r2"])
    for m in ["M0", "M1", "M2", "M3"]:
        add("C true-range R2, fixed split, train-mean benchmark", m, g, F["y_tr"][m]["r2"], s4["y_tr"][m]["r2"],
            f"alpha BC6 {F['y_tr'][m]['alpha']} / repro {s4['y_tr'][m]['alpha']}")
    add("C direction", "accuracy", g, F["direction"]["acc"], s4["direction_control"]["acc"])
    add("C direction", "test share of down days", g, round(1 - F["direction"]["test_share_up"], 4),
        round(1 - s4["direction_control"]["test_share_up"], 4))
    add("C leakage control (same-day news)", "dR2 LEAK-M2, fixed split, step 4 as is", g, F["y_tr"]["d_LEAK_M2"]["v"],
        round(s4["y_tr"]["LEAK"]["r2"] - s4["y_tr"]["M2"]["r2"], 4),
        f"alpha chosen separately: M2 {s4['y_tr']['M2']['alpha']}, LEAK {s4['y_tr']['LEAK']['alpha']}")
    fl = sp["fixed_split_leak_same_alpha"]
    add("C leakage control (same-day news)", "dR2 LEAK-M2, fixed split, same alpha", g, F["y_tr"]["d_LEAK_M2"]["v"],
        fl["delta_LEAK_minus_M2"], f"CI BC6 {ci(F['y_tr']['d_LEAK_M2']['ci'])} / repro {ci(fl['ci95'])}, alpha {fl['alpha_M2_and_LEAK']}")

# cross-market (same in both universes in BC6; taken from the supplement)
sp = json.loads((res / "step4_supplement_mid.json").read_text(encoding="utf-8"))
spm = json.loads((res / "step4_supplement_mega.json").read_text(encoding="utf-8"))
tx = bc6["U1"]["fixed_split"]["taiex"]
for src in [k for k in sp["cross_market"] if k.startswith("taiex")]:
    for t in ["gap", "oc"]:
        add("C cross-market", f"US -> TAIEX {t}: direction accuracy", src, tx[t]["dirAcc"], sp["cross_market"][src][t]["dirAcc"],
            f"n BC6 {tx[t]['n']} / repro {sp['cross_market'][src][t]['n']}")
        add("C cross-market", f"US -> TAIEX {t}: R2", src, tx[t]["r2"], sp["cross_market"][src][t]["r2"])
adr, radr = bc6["U1"]["extra"]["adr2330"], spm["cross_market"]["adr_TSM_to_2330"]
for t in ["gap", "oc"]:
    add("C cross-market", f"TSM ADR -> 2330 {t}: direction accuracy", "2330", adr[t]["dirAcc"], radr[t]["dirAcc"],
        f"n BC6 {adr[t]['n']} / repro {radr[t]['n']}")
    add("C cross-market", f"TSM ADR -> 2330 {t}: R2", "2330", adr[t]["r2"], radr[t]["r2"])

rows = [r for r in rows if r["reproduced"] is not None]
out = Path(sys.argv[3])
with out.open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
for r in rows:
    print(f"{r['section'][:34]:34s} {r['item'][:44]:44s} {r['group'][:14]:14s} {str(r['BC6']):>8s} {str(r['reproduced']):>8s}  {r['note']}")
