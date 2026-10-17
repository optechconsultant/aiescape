"""Amendment 12: EXPLORATORY attempters-only calibration re-analysis (post-hoc; not confirmation). No model calls.

  python analyze_attempters.py > data/attempters_exploratory/analysis.txt

One pass: attempters at 5% (primary), all 12 models (comparison), cutoffs 3% and 10% (sensitivity).
Outcome: a4 deliberate attempt. Method per held-out model as in Amendments 6/7 (P1 = pooled config effects from the
other models in the set + own Firth offset from 48 probe runs; P0 = own probe mean, Jeffreys-smoothed).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_pilot6 import logit_fit, wilson
from evaluate_confirmation import X, boot_D, cal, firth_offset, load, sig

HERE = Path(__file__).parent
OUT = HERE / "data/attempters_exploratory"
SEED = 2026


def probe_mask(g: pd.DataFrame, probes8: set) -> np.ndarray:
    if g.key.isin(probes8).any():
        return g.key.isin(probes8).to_numpy()
    rng, seen, take = np.random.default_rng(SEED), set(), np.zeros(len(g), bool)
    cfg = g.cfg_id.to_numpy()
    for i in rng.permutation(len(g)):
        if cfg[i] not in seen:
            seen.add(cfg[i]); take[i] = True
    return take


def reliability(p, y, bins=10):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    rows = []
    for b in range(bins):
        m = idx == b
        if m.any():
            rows.append((b + 1, int(m.sum()), float(p[m].mean()), float(y[m].mean())))
    return rows


def run_set(df, models, probes8, label, rel_out=None):
    print(f"======== {label}: {len(models)} models: {', '.join(models)}")
    rng = np.random.default_rng(SEED)
    boots, passed, Ds, rows = [], [], [], []
    for m in models:
        tr = df[df.model.isin(models) & (df.model != m)]
        b, _, _ = logit_fit(X(tr), tr.attempt.to_numpy(float))
        g = df[df.model == m].reset_index(drop=True)
        pm = probe_mask(g, probes8)
        yp, yall = g.attempt.to_numpy(float)[pm], g.attempt.to_numpy(float)
        eta = X(g) @ b
        a = firth_offset(eta[pm], yp)
        ev = ~pm
        y, p1 = yall[ev], sig(a + eta[ev])
        p0 = np.full(ev.sum(), (yp.sum() + 0.5) / (pm.sum() + 1))
        cfg = g.cfg_id.to_numpy()[ev]
        b0, b1 = float(np.mean((p0 - y) ** 2)), float(np.mean((p1 - y) ** 2))
        bd = boot_D(y, p0, p1, cfg, rng)
        lo, hi = np.percentile(bd, [2.5, 97.5])
        slope, (slo, shi) = cal(p1, y)
        citl = p1.mean() - y.mean()
        c1 = bool(lo > 0)
        c2 = bool(np.isfinite(slo) and slo <= 1 <= shi and abs(citl) <= 0.05)
        boots.append(bd); passed.append(c1); Ds.append(b0 - b1)
        print(f"  {m:24s} eval n={len(y)} events={int(y.sum()):3d} rate {y.mean():.3f} probe events {int(yp.sum()):2d} | "
              f"Brier own {b0:.4f} P1 {b1:.4f} D {b0 - b1:+.4f} [{lo:+.4f}, {hi:+.4f}] C1 {'PASS' if c1 else 'FAIL'} | "
              f"slope {slope:.2f} [{slo:.2f}, {shi:.2f}] CITL {citl:+.3f} C2 {'PASS' if c2 else 'FAIL'}")
        rows.append(dict(set=label, model=m, n_eval=len(y), events=int(y.sum()), rate=y.mean(), probe_events=int(yp.sum()),
                         brier_own=b0, brier_p1=b1, D=b0 - b1, D_lo=lo, D_hi=hi, C1=c1, slope=slope, slope_lo=slo,
                         slope_hi=shi, citl=citl, C2=c2))
        if rel_out is not None:
            for bn, n, mp, mo in reliability(p1, y):
                rel_out.append(dict(set=label, model=m, bin=bn, n=n, mean_pred=mp, observed=mo))
    pooled = np.mean(np.vstack(boots), axis=0)
    plo, phi = np.percentile(pooled, [2.5, 97.5])
    need = math.ceil(len(models) / 2)
    ok = plo > 0 and sum(passed) >= need
    c2n = sum(r["C2"] for r in rows)
    print(f"  POOLED C1: mean D {np.mean(Ds):+.4f} [{plo:+.4f}, {phi:+.4f}]; per-model {sum(passed)}/{len(models)} pass "
          f"(need {need}) -> {'PASS' if ok else 'FAIL'}.   C2: {c2n}/{len(models)} models pass.\n")
    rows.append(dict(set=label, model="POOLED", D=np.mean(Ds), D_lo=plo, D_hi=phi, C1=ok, C2=f"{c2n}/{len(models)}"))
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.concat([load(HERE / f"data/pilot{p}") for p in (6, 7, 8)], ignore_index=True)
    probes8 = {k for v in json.load(open(HERE / "data/pilot8/probe_sets.json")).values() for k in v}
    st = df.groupby("model").attempt.agg(["size", "sum", "mean"]).sort_values("mean", ascending=False)
    print("STEP 1: a4 attempt rate per model (all runs in the 48-configuration design)")
    tab = []
    for m, r in st.iterrows():
        lo, hi = wilson(int(r["sum"]), int(r["size"]))
        flag = "borderline (3-8%)" if 0.03 <= r["mean"] <= 0.08 else ""
        print(f"  {m:24s} {int(r['sum']):4d}/{int(r['size']):<5d} {r['mean']:6.1%} [{lo:.1%}, {hi:.1%}]  "
              f">=3%:{'Y' if r['mean'] >= .03 else 'n'} >=5%:{'Y' if r['mean'] >= .05 else 'n'} >=10%:{'Y' if r['mean'] >= .10 else 'n'}  {flag}")
        tab.append(dict(model=m, runs=int(r["size"]), attempts=int(r["sum"]), rate=r["mean"], lo=lo, hi=hi,
                        attempter_3=r["mean"] >= .03, attempter_5=r["mean"] >= .05, attempter_10=r["mean"] >= .10))
    pd.DataFrame(tab).to_csv(OUT / "attempt_rates.csv", index=False)
    print()
    rows, rel = [], []
    sets = [("STEP 2: attempters (>= 5%)", st.index[st["mean"] >= .05].tolist()),
            ("STEP 3: all 12 models (no cutoff)", st.index.tolist()),
            ("STEP 4a: attempters (>= 3%)", st.index[st["mean"] >= .03].tolist()),
            ("STEP 4b: attempters (>= 10%)", st.index[st["mean"] >= .10].tolist())]
    for label, ms in sets:
        rows += run_set(df, ms, probes8, label, rel)
    pd.DataFrame(rows).to_csv(OUT / "results.csv", index=False)
    pd.DataFrame(rel).to_csv(OUT / "reliability.csv", index=False)
    print("Reliability tables (deciles of P1; mean predicted vs observed) are in reliability.csv.")


if __name__ == "__main__":
    main()
