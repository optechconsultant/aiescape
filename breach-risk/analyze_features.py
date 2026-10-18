"""Amendment 16 Part 2 + addendum (EXPLORATORY): model features vs behaviour. Facts from paper_data_pack/P2_card_facts*.csv.

  python analyze_features.py            # primary: card-only (starred values = unknown)  -> P2_*.csv
  python analyze_features.py --starred  # sensitivity: starred values included           -> P2_*_sens.csv
"""
from __future__ import annotations

import itertools
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
OUT = HERE.parent / "paper_data_pack"
NUMERIC = ["total_params_B", "active_params_B", "release_days", "capability"]
SENS = "--starred" in sys.argv
SUF = "_sens" if SENS else ""


def fisher_exact(t):
    """Two-sided Fisher exact test on a 2x2 table (sum of hypergeometric probabilities <= observed)."""
    (a, b), (c, d) = t
    r1, c1, n = a + b, a + c, a + b + c + d
    pr = lambda x: math.comb(c1, x) * math.comb(n - c1, r1 - x) / math.comb(n, r1)
    p0 = pr(a)
    p = sum(pr(x) for x in range(max(0, r1 + c1 - n), min(r1, c1) + 1) if pr(x) <= p0 * (1 + 1e-9))
    return ((a * d) / (b * c) if b * c else float("inf")), min(1.0, p)


def clopper(k, n, a=0.05):
    cdf = lambda x, p: sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x + 1))

    def solve(f):
        lo_, hi_ = 0.0, 1.0
        for _ in range(100):
            mid = (lo_ + hi_) / 2
            lo_, hi_ = (mid, hi_) if f(mid) else (lo_, mid)
        return (lo_ + hi_) / 2
    lo = solve(lambda p: 1 - cdf(k - 1, p) < a / 2) if k > 0 else 0.0
    hi = solve(lambda p: cdf(k, p) > a / 2) if k < n else 1.0
    return lo, hi


def spearman_perm(x, y, rng):
    """Spearman rho and two-sided permutation p: full enumeration for n <= 10, 1,000,000 random permutations otherwise."""
    n = len(x)
    rx, ry = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    rxc, ryc = rx - rx.mean(), ry - ry.mean()
    den = math.sqrt((rxc ** 2).sum() * (ryc ** 2).sum())
    if den == 0:
        return np.nan, np.nan, "constant"
    obs = float(rxc @ ryc)
    ge, total = 0, 0
    if n <= 10:
        it = itertools.permutations(ryc)
        while True:
            chunk = np.fromiter(itertools.chain.from_iterable(itertools.islice(it, 200_000)), float).reshape(-1, n)
            if not len(chunk):
                break
            ge += int((np.abs(chunk @ rxc) >= abs(obs) - 1e-9).sum()); total += len(chunk)
        how = f"exact ({total:,} permutations)"
    else:
        for _ in range(10):
            idx = np.argsort(rng.random((100_000, n)), axis=1)
            ge += int((np.abs(ryc[idx] @ rxc) >= abs(obs) - 1e-9).sum()); total += 100_000
        how = "1,000,000 random permutations"
    return obs / den, ge / total, how


def holm(ps, m):
    """Holm step-down over a family of m tests; tests without p-value count in the family but get no adjusted p."""
    ps = np.array(ps, float); out = np.full(len(ps), np.nan)
    order = [i for i in np.argsort(np.where(np.isnan(ps), np.inf, ps)) if not np.isnan(ps[i])]
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * ps[i])); out[i] = run
    return out


def load_facts(path):
    t = pd.read_csv(path, dtype=str)
    t["starred_fields"] = t["starred_fields"].fillna("") if "starred_fields" in t else ""
    for c in ("total_B", "active_B"):
        t[c] = pd.to_numeric(t[c], errors="coerce")
    if not SENS and "starred_fields" in t:  # card-only: starred values are unknown
        for i, r in t.iterrows():
            for f in [s for s in r.starred_fields.split(";") if s]:
                t.loc[i, f] = np.nan if f in ("total_B", "active_B") else None
    t["moe"] = t.moe.map({"moe": "MoE", "dense": "dense"})
    t["reasoning"] = t.reasoning.map({"reasoning": "reasoning", "non-reasoning": "non-reasoning"})
    t.loc[t.moe == "dense", "active_B"] = t.loc[t.moe == "dense", "total_B"]  # dense: active = total (Amendment 16)
    t["release_days"] = t.release_date.apply(lambda s: (date.fromisoformat(s) - date(2025, 1, 1)).days if isinstance(s, str) and s else np.nan)
    return t.rename(columns={"total_B": "total_params_B", "active_B": "active_params_B"})


def main():
    feat = load_facts(OUT / "P2_card_facts.csv")
    caps = pd.read_csv(OUT / "A5_per_model_rates_a4.csv").set_index("model")
    b3 = pd.read_csv(OUT / "B3_setting_effects_long.csv")
    feat["capability"] = feat.model.map(caps.capability_AA_index)
    feat["attempt_rate"] = feat.model.map(caps.attempt_rate)
    feat["swing_blocked_minus_open"] = feat.model.map(b3[b3.setting == "honest_path"].set_index("model")["diff"])
    d = feat[feat.attempt_rate.notna()]
    rng = np.random.default_rng(2026)
    tests = []
    for f in NUMERIC:
        for o in ("attempt_rate", "swing_blocked_minus_open"):
            s = d[d[f].notna()]
            if len(s) >= 3 and s[f].nunique() > 1:
                r, p, how = spearman_perm(s[f].astype(float).to_numpy(), s[o].to_numpy(), rng)
            else:
                r, p, how = np.nan, np.nan, "not testable (fewer than 3 models with data)"
            tests.append(dict(test=f"Spearman {f} vs {o}", n=len(s), statistic=r, p=p, method=how))
    for f, pos in (("moe", "MoE"), ("reasoning", "reasoning")):
        for o in ("attempt_rate", "swing_blocked_minus_open"):
            s = d[d[f].notna()]
            if s[f].nunique() == 2:
                tab = pd.crosstab(s[f] == pos, s[o] >= 0.30).reindex(index=[True, False], columns=[True, False], fill_value=0)
                odds, p = fisher_exact(tab.to_numpy())
                tests.append(dict(test=f"Fisher {f} vs {o}>=30%", n=len(s), statistic=odds, p=p,
                                  method=f"Fisher exact two-sided; {pos}: {int((s[f] == pos).sum())}, other: {int((s[f] != pos).sum())}"))
            else:
                tests.append(dict(test=f"Fisher {f} vs {o}>=30%", n=len(s), statistic=np.nan, p=np.nan,
                                  method=f"not testable ({len(s)} known, {s[f].nunique()} distinct value(s))"))
    t = pd.DataFrame(tests)
    t["p_holm_family12"] = holm(t.p, 12)
    t.to_csv(OUT / f"P2_tests{SUF}.csv", index=False)

    rules, thr = [], {}
    for f in NUMERIC + ["moe", "reasoning"]:
        s = d[d[f].notna()]
        if f == "release_days" or len(s) == 0:
            rules.append(dict(feature=f, n_known=len(s), rule="no rule (fewer than 3 dated models)" if f == "release_days" else "no data", correct="", ci=""))
            continue
        if f in NUMERIC:
            thr[f] = float(s[f].astype(float).median()); pred = s[f].astype(float) > thr[f]; rule = f"{f} > {thr[f]:g} (median of the {len(s)} known)"
        else:
            pos = "MoE" if f == "moe" else "reasoning"; pred = s[f] == pos; rule = f"{f} = {pos}"
        k, n = int((pred == (s.attempt_rate >= 0.30)).sum()), len(s); lo, hi = clopper(k, n)
        rules.append(dict(feature=f, n_known=n, rule=rule + " => attempt rate >= 30%", correct=f"{k}/{n}", ci=f"[{lo:.2f}, {hi:.2f}]"))
    r = pd.DataFrame(rules)
    r.to_csv(OUT / f"P2_rules{SUF}.csv", index=False)

    fr = pd.read_csv(OUT / "P2_card_facts_fresh.csv")
    fr["moe"] = fr.moe.map({"moe": "MoE", "dense": "dense"}); fr["reasoning"] = fr.reasoning.map({"reasoning": "reasoning", "non-reasoning": "non-reasoning"})
    fr = fr.rename(columns={"total_B": "total_params_B", "active_B": "active_params_B"})
    for f in ("total_params_B", "active_params_B"):
        fr[f] = pd.to_numeric(fr[f], errors="coerce")
    for f in ("total_params_B", "active_params_B"):
        if f in thr:
            fr[f"pred_{f}"] = fr[f].apply(lambda v: "unknown" if pd.isna(v) else (">=30%" if v > thr[f] else "<30%"))
    fr["pred_moe"] = fr.moe.apply(lambda v: "unknown" if pd.isna(v) else (">=30%" if v == "MoE" else "<30%"))
    fr["pred_reasoning"] = fr.reasoning.apply(lambda v: "unknown" if pd.isna(v) else (">=30%" if v == "reasoning" else "<30%"))
    fr["pred_capability"] = "unknown (no index)"
    fr.to_csv(OUT / f"P2_fresh_candidates_predictions{SUF}.csv", index=False)
    feat.to_csv(OUT / f"P2_features{SUF}.csv", index=False)

    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
    print("mode:", "SENSITIVITY (starred values included)" if SENS else "PRIMARY (card-only)")
    print(feat.drop(columns=["notes", "starred_fields", "release_date"]).fillna("unknown").to_string(index=False))
    print(t.round(4).fillna("").to_string(index=False))
    print(r.to_string(index=False))
    print("thresholds:", thr)
    print(fr.drop(columns=["notes", "release_date"]).fillna("unknown").to_string(index=False))


if __name__ == "__main__":
    main()
