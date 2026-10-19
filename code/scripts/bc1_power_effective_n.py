"""BC1: how many predictions are needed to tell a directional-accuracy edge from luck.

Part A  analytic sample size for a one-sided binomial test (H0: p = 0.5).
Part B  translate into trading days for three set-ups (one stock, index, N stocks on the same day).
Part C  Monte Carlo check of the design effect when all stocks share a market factor and the
        model's calls are correlated across stocks on the same day.

Usage:  python3 -I bc1_power_effective_n.py <results_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(20261018)

ALPHA, POWER = 0.05, 0.80
z_a, z_b = stats.norm.ppf(1 - ALPHA), stats.norm.ppf(POWER)


def n_required(p1, p0=0.5):
    """Normal-approximation sample size for a one-sided test of p0 vs p1."""
    num = z_a * np.sqrt(p0 * (1 - p0)) + z_b * np.sqrt(p1 * (1 - p1))
    return int(np.ceil((num / (p1 - p0)) ** 2))


def exact_power(n, p1, p0=0.5):
    """Power of the exact one-sided binomial test with n trials."""
    k_crit = stats.binom.ppf(1 - ALPHA, n, p0) + 1  # reject if correct >= k_crit
    return 1 - stats.binom.cdf(k_crit - 1, n, p1)


res = {"alpha": ALPHA, "power": POWER, "partA": [], "partB": {}, "partC": []}

# ---------- Part A ----------
for p1 in [0.51, 0.52, 0.53, 0.55, 0.60]:
    n = n_required(p1)
    res["partA"].append({"accuracy": p1, "n_independent": n,
                         "exact_power_at_n": round(float(exact_power(n, p1)), 3),
                         "half_width_95ci_at_n": round(1.96 * np.sqrt(0.25 / n), 4)})

# ---------- Part B ----------
DAYS_PER_YEAR = 245  # roughly the number of TWSE trading days per year
for p1 in [0.52, 0.55]:
    n = n_required(p1)
    row = {"index_or_one_stock_years": round(n / DAYS_PER_YEAR, 1)}
    for m, rho in [(30, 0.0), (30, 0.1), (30, 0.25), (30, 0.4)]:
        deff = 1 + (m - 1) * rho          # design effect for m correlated calls per day
        days = n * deff / m
        row[f"m{m}_rho{rho}_days"] = int(np.ceil(days))
        row[f"m{m}_rho{rho}_years"] = round(days / DAYS_PER_YEAR, 2)
    res["partB"][str(p1)] = row

# ---------- Part C: Monte Carlo of the design effect ----------
# One-factor market: r_it = beta * f_t + e_it.  The "model" makes a market-level call each day
# (same direction for every stock) that is right about the market with prob q, plus a small
# stock-specific edge.  We compare the naive binomial SE with the day-clustered SE.

def simulate(m=30, days=500, beta_share=0.4, q_market=0.5, reps=400):
    """beta_share = share of daily return variance explained by the market factor."""
    naive_rej, clustered_rej, accs, icc = 0, 0, [], []
    for _ in range(reps):
        f = rng.standard_normal(days)
        e = rng.standard_normal((days, m))
        r = np.sqrt(beta_share) * f[:, None] + np.sqrt(1 - beta_share) * e
        market_call = np.where(rng.random(days) < q_market, np.sign(f), -np.sign(f))
        pred = np.repeat(market_call[:, None], m, axis=1)
        correct = (pred == np.sign(r)).astype(float)
        acc = correct.mean()
        accs.append(acc)
        n = correct.size
        se_naive = np.sqrt(0.25 / n)
        day_means = correct.mean(axis=1)
        se_cluster = day_means.std(ddof=1) / np.sqrt(days)
        naive_rej += (acc - 0.5) / se_naive > z_a
        clustered_rej += (acc - 0.5) / se_cluster > z_a
        # intra-day correlation of correctness (ICC) via one-way ANOVA estimator
        msb = m * day_means.var(ddof=1)
        msw = correct.var(axis=1, ddof=1).mean()
        icc.append((msb - msw) / (msb + (m - 1) * msw))
    return {"m": m, "days": days, "market_var_share": beta_share, "q_market": q_market,
            "mean_acc": round(float(np.mean(accs)), 4),
            "false_positive_rate_naive": round(naive_rej / reps, 3),
            "false_positive_rate_day_clustered": round(clustered_rej / reps, 3),
            "mean_icc": round(float(np.mean(icc)), 3)}

for share in [0.2, 0.4, 0.6]:
    res["partC"].append(simulate(beta_share=share))

(OUT / "bc1_power_effective_n.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
print(json.dumps(res, indent=2, ensure_ascii=False))
