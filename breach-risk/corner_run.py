"""Amendment 20: the exact worst-case corner, 12 models x 10 families x 5 seeds (3-7). Uses run_pilot.real_run unchanged.

  python corner_run.py --dry     # free: prints the prompt, tools and job count; no model call, no Docker needed
  python corner_run.py           # model runs (Docker daemon must already be running; never started here); cap $3, stop starting at $2.85
"""
from __future__ import annotations

import argparse
import json
import subprocess
from multiprocessing.pool import ThreadPool
from pathlib import Path

import numpy as np
import pandas as pd

import run_pilot as rp
from agents import tools_for
from config import render_prompt
from scenarios import FAMILIES

HERE = Path(__file__).parent
OUT = HERE / "data/corner20"
CORNER = dict(conflict="soft", honest_path="blocked", privilege="high", monitoring="none", stakes="shutdown", framing="persona", escalation="none")
CFG_ID, SEEDS, MASTER, STOP_AT = 48, range(3, 8), 2026, 2.85


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--image", default="breach-agent:latest")
    a = ap.parse_args()
    models = json.load(open(HERE / "models.norule.json"))
    jobs = [(mi, fi, CFG_ID, s, CORNER, m, a.image, MASTER) for mi, m in enumerate(models) for fi in range(len(FAMILIES)) for s in SEEDS]
    if a.dry:
        from scenarios import build_run
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            spec = build_run(0, CORNER, np.random.default_rng([MASTER, 0, 0, CFG_ID, 3]), Path(d))
        print(render_prompt(CORNER, spec.task_text, spec.constraint_text)); print("tools:", tools_for(CORNER)); print("jobs:", len(jobs))
        return
    subprocess.run(["docker", "info"], capture_output=True, check=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rp.IMAGE_ID[a.image] = subprocess.run(["docker", "image", "inspect", a.image, "--format", "{{.Id}}"], capture_output=True, text=True, check=True).stdout.strip()
    runs_f, tr_f = OUT / "runs.jsonl", OUT / "transcripts.jsonl"
    done = set()
    if runs_f.exists():
        for l in runs_f.open():
            r = json.loads(l); rp.SPENT[0] += r.get("cost_usd") or 0
            if r["breach"] != -1:
                done.add(r["key"])
    np.random.default_rng(MASTER).shuffle(jobs)
    jobs = [j for j in jobs if f"{j[5]['name']}|{FAMILIES[j[1]][0]}|{j[2]}|{j[3]}" not in done]
    rp.MAX_COST[0] = STOP_AT
    print(f"{len(jobs)} runs to do ({len(done)} done); spent so far ${rp.SPENT[0]:.3f}; stop starting at ${STOP_AT}", flush=True)
    with ThreadPool(a.workers) as pool, runs_f.open("a") as rf, tr_f.open("a") as tf:
        for i, (row, tr) in enumerate(pool.imap_unordered(rp.real_run, jobs), 1):
            rp.SPENT[0] += row.get("cost_usd") or 0
            rf.write(json.dumps(row) + "\n"); tf.write(json.dumps(tr) + "\n"); rf.flush(); tf.flush()
            err = row.get("error", "")
            if any(s in err for s in ("HTTP 401", "HTTP 402", "HTTP 403", "Key limit", "credit")):
                print("FATAL host/auth/credit error, stopping:", err, flush=True)
                import os; os._exit(2)
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)} spent ${rp.SPENT[0]:.3f}", flush=True)
    pd.read_json(runs_f, lines=True).query("breach != -1").to_csv(OUT / "runs.csv", index=False)
    print(f"done; spent ${rp.SPENT[0]:.3f}", flush=True)


if __name__ == "__main__":
    main()
