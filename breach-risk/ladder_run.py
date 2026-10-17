"""Ladder v1-lite model runs (Amendment 9). Level text, scoring and gates live in ladder.py and are not changed here.

  python ladder_run.py --models-file models.ladder.json --out data/ladder_v1 --workers 20 --cap 5

Jobs: model x level (0-7) x family (10) x seed (5), shuffled with --master-seed 2026 (resume keeps the order).
Per-model hard stop: no new run for a model once its reported cost reaches --cap (cumulative over resumes).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

from agents import make_backend
from ladder import MAX_TURNS, act, level_cfg, prompt_for, score_run
from sandbox import DockerSandbox
from scenarios import FAMILIES, build_run

HERE = Path(__file__).parent
LOCK = threading.Lock()
SPENT: dict[str, float] = {}
IMAGE_ID = {}


def one(job, cap, image):
    mi, m, level, fi, seed, master = job
    key = f"{m['name']}|P{level}|{FAMILIES[fi][0]}|{seed}"
    row = {"key": key, "model": m["name"], "model_id": m["model"], "level": level, "family": FAMILIES[fi][0], "seed": seed,
           "host": urlparse(os.environ.get("BASE_URL", "")).hostname or "", "quantization": m.get("quantization", ""),
           "image_id": IMAGE_ID.get(image, "")}
    with LOCK:
        if SPENT.get(m["name"], 0) >= cap:
            row.update(severity=-1, error=f"skipped: ${cap} cap reached for {m['name']}")
            return row, {"key": key, "error": row["error"]}
    try:
        with tempfile.TemporaryDirectory() as d:
            spec = build_run(fi, level_cfg(level), np.random.default_rng([master, mi, level, fi, seed]), Path(d))
            prompt = prompt_for(level, spec.task_text)
            backend = make_backend(m)
            with DockerSandbox(image) as sb:
                sb.load(Path(d))
                commands, stdout, meta = act(backend, prompt, sb, level, MAX_TURNS)
                res = score_run(commands, stdout, sb, spec, level, meta["final_message"])
        row.update(res, model_turns=meta["model_turns"], hit_turn_limit=meta["hit_turn_limit"], n_commands=len(commands),
                   cost_usd=round(getattr(backend, "cost", 0.0), 6), providers=",".join(sorted(getattr(backend, "providers", set()))),
                   tokens_in=getattr(backend, "tokens_in", 0), tokens_out=getattr(backend, "tokens_out", 0), error="")
        tr = {"key": key, "prompt": prompt, "commands": commands, "texts": meta["texts"], "final_message": meta["final_message"],
              "stdout": stdout[:20000], "canary": spec.canary, "answer": spec.answer}
    except Exception as e:
        row.update(severity=-1, error=repr(e)[:1000], cost_usd=0)
        tr = {"key": key, "error": repr(e)[:1000]}
    return row, tr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-file", default="models.ladder.json")
    ap.add_argument("--out", default="data/ladder_v1")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--cap", type=float, default=5.0)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--master-seed", type=int, default=2026)
    ap.add_argument("--image", default="breach-agent:latest")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    IMAGE_ID[a.image] = subprocess.run(["docker", "image", "inspect", a.image, "--format", "{{.Id}}"],
                                       capture_output=True, text=True, check=True).stdout.strip()
    models = json.loads(Path(a.models_file).read_text())
    out = HERE / a.out
    out.mkdir(parents=True, exist_ok=True)
    runs_f, tr_f = out / "runs.jsonl", out / "transcripts.jsonl"
    done = set()
    if runs_f.exists():
        for l in runs_f.open():
            r = json.loads(l)
            SPENT[r["model"]] = SPENT.get(r["model"], 0) + (r.get("cost_usd") or 0)
            if r["severity"] != -1:
                done.add(r["key"])
    jobs = [(mi, m, lv, fi, s, a.master_seed) for mi, m in enumerate(models) for lv in range(8)
            for fi in range(len(FAMILIES)) for s in range(a.seeds)]
    np.random.default_rng(a.master_seed).shuffle(jobs)
    jobs = [j for j in jobs if f"{j[1]['name']}|P{j[2]}|{FAMILIES[j[3]][0]}|{j[4]}" not in done]
    if a.limit:
        jobs = jobs[:a.limit]
    print(f"{len(jobs)} runs to do ({len(done)} done); spent so far {SPENT}", flush=True)
    from multiprocessing.pool import ThreadPool
    with ThreadPool(a.workers) as pool, runs_f.open("a") as rf, tr_f.open("a") as tf:
        for i, (row, tr) in enumerate(pool.imap_unordered(lambda j: one(j, a.cap, a.image), jobs), 1):
            with LOCK:
                SPENT[row["model"]] = SPENT.get(row["model"], 0) + (row.get("cost_usd") or 0)
            rf.write(json.dumps(row) + "\n"); tf.write(json.dumps(tr) + "\n"); rf.flush(); tf.flush()
            if i % 25 == 0:
                print(f"  {i}/{len(jobs)}  spent {({k: round(v, 3) for k, v in SPENT.items()})}", flush=True)
    print("done", {k: round(v, 3) for k, v in SPENT.items()})


if __name__ == "__main__":
    main()
