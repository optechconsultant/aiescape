"""Amendment 14 frozen prediction: pooled configuration effects of the 10 attempters (Amendment 12 set), no
per-model offset, no probe runs. Scores all 1,458 combinations; saves the top 24 and bottom 24 with scores.
Run ONCE before any fresh-model run; never recompute afterwards.

  python fresh_predict.py   # -> data/fresh_ranking/predictions.json
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_pilot6 import logit_fit
from config import FACTORS, d_optimal, full_grid
from evaluate_confirmation import FACT, X, load

HERE = Path(__file__).parent
OUT = HERE / "data/fresh_ranking"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.concat([load(HERE / f"data/pilot{p}") for p in (6, 7, 8)], ignore_index=True)
    rates = df.groupby("model").attempt.mean()
    att = sorted(rates[rates >= 0.05].index)
    tr = df[df.model.isin(att)]
    b, se, conv = logit_fit(X(tr), tr.attempt.to_numpy(float))
    grid = pd.DataFrame(full_grid())
    grid["grid_id"] = range(len(grid))
    eta = X(grid) @ b
    grid["score_logit"], grid["score_prob"] = eta, 1 / (1 + np.exp(-eta))
    design = [json.dumps(c, sort_keys=True) for c in d_optimal(48, seed=2026)[0]]
    grid["in_48_design"] = [json.dumps({k: r[k] for k in FACTORS}, sort_keys=True) in design for _, r in grid.iterrows()]
    order = grid.sort_values(["score_logit", "grid_id"], ascending=[False, True])
    top, bot = order.head(24), order.tail(24).iloc[::-1]
    rec = lambda d: [dict(grid_id=int(r.grid_id), **{k: r[k] for k in FACTORS}, score_logit=round(float(r.score_logit), 6),
                          score_prob=round(float(r.score_prob), 6), in_48_design=bool(r.in_48_design)) for _, r in d.iterrows()]
    out = {"fitted_on": att, "n_runs": int(len(tr)), "converged": bool(conv),
           "coefficients": dict(zip(["intercept"] + [f"{f}={l}" for f, lv in FACT.items() for l in lv[1:]], np.round(b, 6).tolist())),
           "top24": rec(top), "bottom24": rec(bot)}
    p = OUT / "predictions.json"
    p.write_text(json.dumps(out, indent=1))
    print("sha256", hashlib.sha256(p.read_bytes()).hexdigest())
    print("fitted on", att, len(tr), "runs; converged", conv)
    for name, d in (("TOP 24", top), ("BOTTOM 24", bot)):
        print(f"\n{name}: prob {d.score_prob.min():.3f}-{d.score_prob.max():.3f}; in 48-design: {int(d.in_48_design.sum())} "
              f"({', '.join(str(int(i)) for i in d[d.in_48_design].grid_id)})")
        for f in FACTORS:
            print(f"  {f:12s} {dict(Counter(d[f]))}")


if __name__ == "__main__":
    main()
