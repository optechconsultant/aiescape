"""EXPLORATORY recalibration check (no confirmatory claim), pilots 6-8, 12 models.

  python analyze_recal.py > data/recal/analysis_recal.txt

For each held-out model m:
  eta     = pooled configuration effects fitted on the other 11 models (logistic, 7 factors, no model terms)
  current = sigmoid(a + eta),     a from m's 48 probe runs (one-parameter Firth offset)
  scaled  = sigmoid(a + s * eta), a and s from the same 48 probe runs (two-parameter Firth)
Scored on m's remaining runs: Brier, calibration slope (Wald 95% CI), calibration in the large (mean p - rate).
Probe set: pilot8 models use data/pilot8/probe_sets.json; pilot6/7 models take one run per configuration from a
seeded shuffle (seed 2026). Robustness: 200 random probe draws (one run per configuration) per model.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_pilot6 import logit_fit
from evaluate_confirmation import X, firth_offset, load, sig

HERE = Path(__file__).parent
DRAWS, SEED = 200, 2026


def cal(p, y):
    if y.min() == y.max():
        return np.nan, np.nan, np.nan
    lp = np.log(np.clip(p, 1e-9, 1 - 1e-9) / (1 - np.clip(p, 1e-9, 1 - 1e-9)))
    b, se, _ = logit_fit(np.column_stack([np.ones(len(y)), lp]), y)
    return b[1], b[1] - 1.96 * se[1], b[1] + 1.96 * se[1]


def one_per_config(cfg, rng):
    take = np.zeros(len(cfg), bool)
    seen = set()
    for i in rng.permutation(len(cfg)):
        if cfg[i] not in seen:
            seen.add(cfg[i]); take[i] = True
    return take


def fit_both(eta, y, probe):
    a = firth_offset(eta[probe], y[probe])
    b, _, _ = logit_fit(np.column_stack([np.ones(probe.sum()), eta[probe]]), y[probe], firth=True)
    ev = ~probe
    return y[ev], sig(a + eta[ev]), sig(b[0] + b[1] * eta[ev]), b[1]


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def main():
    df = pd.concat([load(HERE / f"data/pilot{p}") for p in (6, 7, 8)], ignore_index=True)
    probes8 = {k for v in json.load(open(HERE / "data/pilot8/probe_sets.json")).values() for k in v}
    models = sorted(df.model.unique())
    rows = []
    for out in ["attempt", "read"]:
        print(f"======== outcome: {out}" + (" (primary)" if out == "attempt" else ""))
        print(f"  {'model':24s} {'rate':>5s} | {'Brier cur':>9s} {'Brier scl':>9s} {'diff':>8s} | "
              f"{'slope cur [95%]':>21s} {'slope scl [95%]':>21s} | {'CITL cur':>8s} {'CITL scl':>8s} | "
              f"{'s':>5s} | draws: scl better, median diff")
        for m in models:
            tr, g = df[df.model != m], df[df.model == m].reset_index(drop=True)
            b, _, _ = logit_fit(X(tr), tr[out].to_numpy(float))
            eta, y, cfg = X(g) @ b, g[out].to_numpy(float), g.cfg_id.to_numpy()
            probe = g.key.isin(probes8).to_numpy() if m in set(df[df.key.isin(probes8)].model) \
                else one_per_config(cfg, np.random.default_rng(SEED))
            ye, pc, ps, s = fit_both(eta, y, probe)
            bc, bs = brier(pc, ye), brier(ps, ye)
            sc, sp = cal(pc, ye), cal(ps, ye)
            rng = np.random.default_rng(SEED + 1)
            d = []
            for _ in range(DRAWS):
                ye2, pc2, ps2, _ = fit_both(eta, y, one_per_config(cfg, rng))
                d.append(brier(pc2, ye2) - brier(ps2, ye2))
            d = np.array(d)
            print(f"  {m:24s} {ye.mean():5.3f} | {bc:9.4f} {bs:9.4f} {bc - bs:+8.4f} | "
                  f"{sc[0]:5.2f} [{sc[1]:5.2f}, {sc[2]:5.2f}] {sp[0]:5.2f} [{sp[1]:5.2f}, {sp[2]:5.2f}] | "
                  f"{pc.mean() - ye.mean():+8.3f} {ps.mean() - ye.mean():+8.3f} | {s:5.2f} | "
                  f"{(d > 0).mean():4.0%}, {np.median(d):+.4f}")
            rows.append(dict(outcome=out, model=m, rate=ye.mean(), brier_cur=bc, brier_scl=bs, diff=bc - bs,
                             slope_cur=sc[0], slope_cur_lo=sc[1], slope_cur_hi=sc[2],
                             slope_scl=sp[0], slope_scl_lo=sp[1], slope_scl_hi=sp[2],
                             citl_cur=pc.mean() - ye.mean(), citl_scl=ps.mean() - ye.mean(), scale=s,
                             draws_scl_better=(d > 0).mean(), draws_median_diff=np.median(d)))
        print()
    out_dir = HERE / "data/recal"
    out_dir.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(out_dir / "recal.csv", index=False)


if __name__ == "__main__":
    main()
