"""Amendment 19 addendum (POST HOC, labelled): Scout sensitivity, leave-one-out, ties. Same code as the committed P1/P2.

  python sensitivity_scen19.py [suffix]   # -> paper_data_pack/S19_sensitivity*.csv, data/scen19/sensitivity_output*.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_behaviour import exact_spearman
from analyze_scen19 import boot

HERE = Path(__file__).parent
OUT = HERE.parent / "paper_data_pack"
SFX = sys.argv[1] if len(sys.argv) > 1 else ""
PAIRS = (("P1", "old_a4_rate"), ("P2", "persistence"))


def run(t):
    """Exactly as committed: pooled rate vs each column, one-sided exact p, 2,000-resample bootstrap (seed 2026, P1 then P2)."""
    rng, res = np.random.default_rng(2026), {}
    for name, col in PAIRS:
        x, y = t.pooled_rate.to_numpy(float), t[col].to_numpy(float)
        rho, p = exact_spearman(x, y, one_sided=True)
        lo, hi = boot(x, y, rng)
        res[name] = dict(rho=rho, p=p, lo=lo, hi=hi, meets_bar=bool(rho >= 0.5 and p < 0.05))
    return res


def main():
    t = pd.read_csv(OUT / f"S19_per_model{SFX}.csv", index_col=0).sort_index()  # alphabetical, as in the committed analysis (bootstrap draws depend on row order)
    rows = []
    allr = run(t)
    for lab, d in (("all models (n=%d)" % len(t), t), ("without llama-4-scout (n=%d)" % (len(t) - 1), t.drop("llama-4-scout"))):
        r = run(d)
        for k in ("P1", "P2"):
            rows.append(dict(set=lab, test=k, n=len(d), rho=r[k]["rho"], p_one_sided_exact=r[k]["p"], boot_lo=r[k]["lo"], boot_hi=r[k]["hi"], meets_bar=r[k]["meets_bar"]))
    main_df = pd.DataFrame(rows)
    loo = []
    for m in t.index:
        r = run(t.drop(m))
        loo.append(dict(dropped=m, n=len(t) - 1, P1_rho=r["P1"]["rho"], P1_p=r["P1"]["p"], P1_meets_bar=r["P1"]["meets_bar"],
                        P2_rho=r["P2"]["rho"], P2_p=r["P2"]["p"], P2_meets_bar=r["P2"]["meets_bar"]))
    loo = pd.DataFrame(loo)
    rk = t.pooled_rate.rank()
    ties = t.pooled_rate.value_counts()
    tie_info = dict(models_with_pooled_rate_exactly_0=int((t.pooled_rate == 0).sum()), distinct_pooled_values=int(t.pooled_rate.nunique()),
                    tied_groups=int((ties > 1).sum()), models_in_tied_groups=int(ties[ties > 1].sum()),
                    zero_without_scout=int((t.drop("llama-4-scout").pooled_rate == 0).sum()))
    main_df.to_csv(OUT / f"S19_sensitivity{SFX}.csv", index=False)
    loo.to_csv(OUT / f"S19_leave_one_out{SFX}.csv", index=False)
    pd.set_option("display.width", 220)
    txt = [main_df.round(4).to_string(index=False), "", loo.round(4).to_string(index=False), "", str(tie_info),
           "pooled rate ranks (average ranks for ties): " + ", ".join(f"{m.split('-')[0]}={r:g}" for m, r in rk.sort_values().items())]
    s = "\n".join(txt); print(s)
    (HERE / f"data/scen19/sensitivity_output{SFX}.txt").write_text(s + "\n")


if __name__ == "__main__":
    main()
