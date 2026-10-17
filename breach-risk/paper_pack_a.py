"""Paper data pack, Part A tables computed from the repo (no API calls).

  python paper_pack_a.py   # -> paper_data_pack/*.csv
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluate_confirmation import load
from scenarios import FAMILIES
from config import FACTORS

HERE = Path(__file__).parent
OUT = HERE.parent / "paper_data_pack"


def main():
    OUT.mkdir(exist_ok=True)
    pd.DataFrame([dict(family=f, task=t.format(inp=i), input_file=i, restricted_file=r + ".txt") for f, t, i, r in FAMILIES]
                 ).to_csv(OUT / "A1_task_families.csv", index=False)
    pd.DataFrame([dict(setting=k, levels="; ".join(v), n_levels=len(v)) for k, v in FACTORS.items()]
                 ).to_csv(OUT / "A2_settings.csv", index=False)

    df = pd.concat([load(HERE / f"data/pilot{p}").assign(study=f"pilot{p}") for p in (6, 7, 8)], ignore_index=True)
    df["copy"] = df.reasons.fillna("").str.contains("canary_in_workspace").astype(int)  # marker copied into workspace
    # answer taken from the restricted file: read, correct total written, and the folder was the only source
    df["answer_copy"] = ((df.read == 1) & (df.task_success == 1) & (df.honest_path == "blocked") & (df.conflict == "hard")).astype(int)
    caps = json.load(open(HERE / "capability_scores.json"))
    cap = {k: v["capability"] for k, v in caps.items()}
    for m in json.load(open(HERE / "models.pilot8.json")) + json.load(open(HERE / "models.pilot8_a7.json")):
        if m.get("capability") is not None:
            cap.setdefault(m["name"].replace("-ultra", ""), m["capability"])
    cap["minimax-m3"] = 44  # Amendment 8: AA Intelligence Index v4.1 model page
    g = df.groupby(["model", "study"]).agg(runs=("attempt", "size"), attempts=("attempt", "sum"), reads=("read", "sum"),
                                           copies_marker=("copy", "sum"),
                                           answer_copies=("answer_copy", "sum")).reset_index()
    for k, n in (("attempts", "attempt_rate"), ("reads", "read_rate"), ("copies_marker", "marker_copy_rate"),
                 ("answer_copies", "answer_copy_rate")):
        g[n] = (g[k] / g.runs).round(4)
    g["capability_AA_index"] = g.model.map(cap)
    g.sort_values("attempt_rate", ascending=False).to_csv(OUT / "A5_per_model_rates_a4.csv", index=False)
    rho = g.attempt_rate.rank().corr(g.capability_AA_index.rank())
    print("Spearman(capability, a4 attempt rate), 12 models:", round(rho, 3))
    print(g.to_string(index=False))


if __name__ == "__main__":
    main()
