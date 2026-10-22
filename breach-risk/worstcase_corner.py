"""Worst-case corner check (EXPLORATORY, free, existing data only: pilots 6-8, rule a4). No scorer, design file or result is changed.

  python worstcase_corner.py   # -> paper_data_pack/W_*.csv, data/worstcase_output.txt
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import report
from analyze_behaviour import exact_spearman
from analyze_features import clopper
from config import FACTORS as _F

FACTORS = list(_F)

HERE = Path(__file__).parent
OUT = HERE.parent / "paper_data_pack"
# riskiest level of each setting: as defined by the person running the study (soft conflict, blocked, highest privilege,
# no monitoring, highest stakes) and, for framing and escalation, the level with the highest pooled attempt rate (B3 table)
CORNER = dict(conflict="soft", honest_path="blocked", privilege="high", monitoring="none", stakes="shutdown", framing="persona", escalation="none")


def main():
    designs = [json.load(open(HERE / f"data/pilot{p}/design.json")) for p in (5, 6, 8)]
    same = all(d == designs[0] for d in designs)
    design = designs[0]
    out = [f"design files pilot5/6/8 identical: {same}; configurations: {len(design)}", f"corner: {CORNER}"]
    exact = [i for i, c in enumerate(design) if c == CORNER]
    dist = [sum(c[f] != CORNER[f] for f in FACTORS) for c in design]
    best = min(dist)
    near = [i for i, d in enumerate(dist) if d == best]
    out.append(f"exact corner among the {len(design)} combinations: {bool(exact)}; minimum number of differing settings: {best}")
    for i in near:
        out.append(f"  closest: design index {i}: {design[i]}  differs in: {[f for f in FACTORS if design[i][f] != CORNER[f]]}")
    report.RULE = "a4"
    df = pd.concat([report.load(HERE / f"data/pilot{p}").assign(study=f"pilot{p}") for p in (6, 7, 8)], ignore_index=True)
    key = lambda c: tuple(c[f] for f in FACTORS)
    cfg_keys = df[FACTORS].apply(tuple, axis=1)
    rows = []
    for tag, idxs in (("closest", near),):
        for i in idxs:
            sel = cfg_keys == key(design[i])
            for m, g in df.groupby("model"):
                gg = g[sel[g.index]]
                k, n = int(gg.deliberate_attempt.sum()), len(gg)
                lo, hi = clopper(k, n)
                rows.append(dict(design_index=i, model=m, runs=n, attempts=k, rate=k / n if n else np.nan, ci_lo=lo, ci_hi=hi))
    r = pd.DataFrame(rows)
    overall = df.groupby("model").deliberate_attempt.agg(["mean", "size"]).rename(columns={"mean": "overall_rate", "size": "overall_runs"})
    res = []
    for i in near:
        t = r[r.design_index == i].set_index("model").join(overall)
        t["corner_ge_overall"] = t.rate >= t.overall_rate
        rho, p = exact_spearman(t.rate.to_numpy(), t.overall_rate.to_numpy(), one_sided=True)
        t["rank_corner"] = t.rate.rank(ascending=False); t["rank_overall"] = t.overall_rate.rank(ascending=False)
        t.sort_values("overall_rate", ascending=False).to_csv(OUT / f"W_corner_design{i}.csv")
        pd.set_option("display.width", 220)
        out.append(f"\nclosest combination = design index {i}: {design[i]}")
        out.append(t.sort_values("overall_rate", ascending=False)[["runs", "attempts", "rate", "ci_lo", "ci_hi", "overall_rate", "overall_runs", "corner_ge_overall"]].round(3).to_string())
        out.append(f"Spearman(corner rate, overall rate) = {rho:.4f}, one-sided exact p = {p:.4f} (descriptive); models with corner rate >= overall: {int(t.corner_ge_overall.sum())}/12; "
                   f"corner rate under 5%: {int((t.rate < 0.05).sum())}")
    s = "\n".join(out); print(s)
    (HERE / "data/worstcase_output.txt").write_text(s + "\n")


if __name__ == "__main__":
    main()
