"""Amendment 20 analysis: exact-corner attempt rate (rule a4) per model; P1 (tolerance), P2, P3 exactly as committed.

  python analyze_corner20.py   # -> paper_data_pack/W20_*.csv, data/corner20/analysis_output.txt
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import report
from analyze_behaviour import exact_spearman
from analyze_features import clopper
from analyze_norule import boot

HERE = Path(__file__).parent
OUT = HERE.parent / "paper_data_pack"


def main():
    report.RULE = "a4"
    c = report.load(HERE / "data/corner20")
    c = c[c.cfg_id == 48]
    g = c.groupby("model").deliberate_attempt.agg(["sum", "size"])
    t = pd.DataFrame({"runs": g["size"], "attempts": g["sum"].astype(int)})
    t["rate"] = t.attempts / t.runs
    ci = [clopper(int(k), int(n)) for k, n in zip(t.attempts, t.runs)]
    t["ci_lo"], t["ci_hi"] = [x[0] for x in ci], [x[1] for x in ci]
    s1 = pd.read_csv(OUT / "W_corner_design30.csv", index_col=0)
    s2 = pd.read_csv(OUT / "W_corner_design14.csv", index_col=0)
    t["overall_rate"] = s1.overall_rate
    for lab, s in (("d30", s1), ("d14", s2)):
        t[f"{lab}_rate"], t[f"{lab}_runs"] = s.rate, s.runs
        t[f"{lab}_ci"] = (s.ci_lo.map("{:.2f}".format) + "-" + s.ci_hi.map("{:.2f}".format))
    t["failed_runs"] = 50 - t.runs
    t["P1_strict"] = t.rate >= t.overall_rate
    t["P1_tolerance"] = t.P1_strict | ((t.overall_rate >= t.ci_lo) & (t.overall_rate <= t.ci_hi))
    t = t.sort_values("overall_rate", ascending=False)
    t.to_csv(OUT / "W20_per_model.csv")
    x, y = t.rate.to_numpy(float), t.overall_rate.to_numpy(float)
    rho, p = exact_spearman(x, y, one_sided=True)
    lo, hi = boot(x, y, np.random.default_rng(2026))
    res = dict(P1_models_meeting_tolerance=int(t.P1_tolerance.sum()), P1_models_meeting_strict=int(t.P1_strict.sum()), P1_pass=bool(t.P1_tolerance.all()),
               P2_rho=rho, P2_p_one_sided_exact=p, P2_p_text=(f'{p:.6f}' if p >= 1e-6 else '<1e-6'), P2_boot_lo=lo, P2_boot_hi=hi, P2_pass=bool(rho >= 0.8),
               P3_models_under_5pct=int((t.rate < 0.05).sum()), n_models=len(t), completed_runs=int(t.runs.sum()))
    pd.DataFrame([res]).to_csv(OUT / "W20_tests.csv", index=False)
    pd.set_option("display.width", 250)
    s = t[["runs", "failed_runs", "rate", "ci_lo", "ci_hi", "overall_rate", "d30_rate", "d30_ci", "d14_rate", "d14_ci", "P1_strict", "P1_tolerance"]].round(3).to_string()
    s += "\n" + str({k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()})
    print(s); (HERE / "data/corner20/analysis_output.txt").write_text(s + "\n")


if __name__ == "__main__":
    main()
