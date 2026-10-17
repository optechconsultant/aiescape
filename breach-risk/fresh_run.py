"""Amendment 14 fresh-model runs. Harness = run_pilot.real_run unchanged (same prompts, tools, 24 turns, scorer, image).

  python fresh_run.py --model NAME --phase screen|main [--per-combo 20] --cap 15
Combinations come from the frozen data/fresh_ranking/predictions.json (never recomputed).
Run r (0-based) of a combination uses task family r % 10 and seed r // 10, so screen runs (r = 0..9) are reused
as the first 10 main runs. Key: name|family|grid_id|seed (as in run_pilot).
"""
from __future__ import annotations

import argparse
import json
import subprocess
from multiprocessing.pool import ThreadPool
from pathlib import Path

import pandas as pd

import run_pilot
from config import FACTORS
from scenarios import FAMILIES

HERE = Path(__file__).parent
OUT = HERE / "data/fresh_ranking"


def combos():
    p = json.load(open(OUT / "predictions.json"))
    return p["top24"], p["bottom24"]


def total_spent():
    f = OUT / "runs.jsonl"
    return sum((json.loads(l).get("cost_usd") or 0) for l in f.open()) if f.exists() else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--phase", choices=["screen", "main"], required=True)
    ap.add_argument("--per-combo", type=int, default=20)
    ap.add_argument("--cap", type=float, default=15.0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--image", default="breach-agent:latest")
    a = ap.parse_args()
    m = next(x for x in json.load(open(HERE / "models.fresh.json")) if x["name"] == a.model)
    top, bot = combos()
    sel = (top[:5] + bot[:5]) if a.phase == "screen" else (top + bot)
    n = 10 if a.phase == "screen" else a.per_combo
    run_pilot.IMAGE_ID[a.image] = subprocess.run(["docker", "image", "inspect", a.image, "--format", "{{.Id}}"],
                                                 capture_output=True, text=True, check=True).stdout.strip()
    runs_f, tr_f = OUT / "runs.jsonl", OUT / "transcripts.jsonl"
    done = set()
    if runs_f.exists():
        done = {json.loads(l)["key"] for l in runs_f.open() if json.loads(l)["breach"] != -1}
    jobs = []
    for c in sel:
        cfg = {k: c[k] for k in FACTORS}
        for r in range(n):
            fi, seed = r % len(FAMILIES), r // len(FAMILIES)
            key = f"{m['name']}|{FAMILIES[fi][0]}|{c['grid_id']}|{seed}"
            if key not in done:
                jobs.append((0, fi, c["grid_id"], seed, cfg, m, a.image, 2026))
    spent = total_spent()
    run_pilot.SPENT[0], run_pilot.MAX_COST[0] = spent, a.cap  # cumulative cap across all models and phases
    print(f"{a.model} {a.phase}: {len(jobs)} runs to do; total spent so far ${spent:.3f}", flush=True)
    with ThreadPool(a.workers) as pool, runs_f.open("a") as rf, tr_f.open("a") as tf:
        for i, (row, tr) in enumerate(pool.imap_unordered(run_pilot.real_run, jobs), 1):
            run_pilot.SPENT[0] += row.get("cost_usd") or 0
            row["phase"] = a.phase
            rf.write(json.dumps(row) + "\n"); tf.write(json.dumps(tr) + "\n"); rf.flush(); tf.flush()
            if i % 50 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} total spent ${run_pilot.SPENT[0]:.3f}", flush=True)
    d = pd.read_json(runs_f, lines=True)
    d = d[d.model == a.model]
    print(f"done {a.model}: completed {(d.breach != -1).sum()}, failed {(d.breach == -1).sum()}; "
          f"errors: {d[d.breach == -1].error.str[:120].value_counts().head(3).to_dict()}")


if __name__ == "__main__":
    main()
