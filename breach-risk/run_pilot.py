"""Run the factorial experiment. Currently supports --mode dryrun (scripted, synthetic agents).

  python run_pilot.py --design-only
  python run_pilot.py --mode dryrun --seeds 2 --out data/dryrun_synthetic
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from config import FACTORS, d_optimal, design_row, feature_names, full_grid
from sandbox import LocalSandbox
from scenarios import FAMILIES, build_run
from scorer import score
from simulation import ScriptedAgent, family_effects, simulated_models

HERE = Path(__file__).parent
TMP = os.environ.get("BREACH_TMP", tempfile.gettempdir())


def design_report(design, d_eff):
    X = np.array([design_row(c) for c in design])
    rand_eff = []
    grid = full_grid()
    rng = np.random.default_rng(0)
    for _ in range(200):
        Xr = np.array([design_row(grid[i]) for i in rng.choice(len(grid), len(design), replace=False)])
        s, ld = np.linalg.slogdet(Xr.T @ Xr)
        rand_eff.append(np.exp(ld / X.shape[1]) / len(design) if s > 0 else 0.0)
    print(f"full grid: {len(grid)} configurations; design: {len(design)} runs, {X.shape[1]} parameters")
    print(f"model-matrix rank: {np.linalg.matrix_rank(X)} / {X.shape[1]}")
    print(f"D-efficiency: {d_eff:.3f}   (random 48-run designs: mean {np.mean(rand_eff):.3f}, best {np.max(rand_eff):.3f})")
    for f, levels in FACTORS.items():
        counts = [sum(c[f] == lv for c in design) for lv in levels]
        print(f"  {f:12s} " + "  ".join(f"{lv}={n}" for lv, n in zip(levels, counts)))


def one_run(job):
    mi, fi, ci, seed, cfg, model, v_family, master = job
    rng = np.random.default_rng([master, mi, fi, ci, seed])
    with tempfile.TemporaryDirectory(dir=TMP) as d:
        root = Path(d)
        spec = build_run(fi, cfg, rng, root)
        sb = LocalSandbox(root)
        commands, stdout, meta = ScriptedAgent().act(spec, cfg, model, v_family, rng, sb)
        res = score(commands, stdout, sb, spec)
    return {"source": "synthetic", "model": model.name, "rl_heavy": model.rl_heavy, "capability": round(model.capability, 3),
            "family": spec.family, "cfg_id": ci, "seed": seed, **cfg, **res, **meta}


def real_run(job):
    """One run with a REAL model inside a disposable Docker container (no network)."""
    from agents import ApiAgent, make_backend, tools_for
    from config import render_prompt
    from sandbox import DockerSandbox

    mi, fi, ci, seed, cfg, m, image, master = job
    rng = np.random.default_rng([master, mi, fi, ci, seed])
    key = f"{m['name']}|{FAMILIES[fi][0]}|{ci}|{seed}"
    env = {"DEPLOY_ENV": "staging", "DEPLOY_TOKEN": "decoy-" + rng.bytes(4).hex()} if cfg["privilege"] == "high" else {}
    row = {"key": key, "source": "real", "model": m["name"], "rl_heavy": m["rl_heavy"], "capability": m["capability"],
           "family": FAMILIES[fi][0], "cfg_id": ci, "seed": seed, **cfg}
    try:
        with tempfile.TemporaryDirectory(dir=TMP) as d:
            root = Path(d)
            spec = build_run(fi, cfg, rng, root)
            with DockerSandbox(image, env) as sb:
                sb.load(root)
                prompt = render_prompt(cfg, spec.task_text, spec.constraint_text)
                commands, stdout, meta = ApiAgent(make_backend(m)).act(prompt, sb, tools_for(cfg))
                res = score(commands, stdout, sb, spec)
        row.update(res, **meta, error="")
        transcript = {"key": key, "prompt": prompt, "commands": commands, "stdout": stdout[:20000], "reasons": res["reasons"]}
    except Exception as e:  # keep going; failed runs are logged, not silently dropped
        row.update(breach=-1, error=repr(e)[:300])
        transcript = {"key": key, "error": repr(e)[:300]}
    return row, transcript


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="dryrun", choices=["dryrun", "real"])
    ap.add_argument("--design-only", action="store_true")
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--models", type=int, default=8)
    ap.add_argument("--master-seed", type=int, default=2026)
    ap.add_argument("--out", default="data/dryrun_synthetic")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--models-file", default="models.json", help="real mode: list of models (see models.example.json)")
    ap.add_argument("--image", default="breach-agent:latest", help="real mode: Docker image (see Dockerfile)")
    ap.add_argument("--limit", type=int, default=0, help="real mode: run only the first N jobs (smoke test)")
    a = ap.parse_args()

    design, d_eff = d_optimal(48, seed=a.master_seed)
    design_report(design, d_eff)
    out = HERE / a.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "design.json").write_text(json.dumps(design, indent=1))
    if a.design_only:
        return

    if a.mode == "real":
        from multiprocessing.pool import ThreadPool
        models = json.loads(Path(a.models_file).read_text())
        done = set()
        runs_f, tr_f = out / "runs.jsonl", out / "transcripts.jsonl"
        if runs_f.exists():  # resume
            done = {json.loads(l)["key"] for l in runs_f.open() if l.strip() and json.loads(l)["breach"] != -1}
        jobs = [(mi, fi, ci, s, cfg, m, a.image, a.master_seed)
                for mi, m in enumerate(models) for fi in range(len(FAMILIES))
                for ci, cfg in enumerate(design) for s in range(a.seeds)
                if f"{m['name']}|{FAMILIES[fi][0]}|{ci}|{s}" not in done]
        if a.limit:
            jobs = jobs[:a.limit]
        print(f"real mode: {len(jobs)} runs ({len(done)} already done) on {a.workers} workers")
        with ThreadPool(a.workers) as pool, runs_f.open("a") as rf, tr_f.open("a") as tf:
            for i, (row, tr) in enumerate(pool.imap_unordered(real_run, jobs), 1):
                rf.write(json.dumps(row) + "\n"); tf.write(json.dumps(tr) + "\n"); rf.flush(); tf.flush()
                if i % 25 == 0:
                    print(f"  {i}/{len(jobs)}")
        pd.read_json(runs_f, lines=True).query("breach != -1").to_csv(out / "runs.csv", index=False)
        print(f"-> {out / 'runs.csv'}  (failed runs stay in runs.jsonl with breach=-1)")
        return

    models, v = simulated_models(a.models), family_effects(len(FAMILIES))
    jobs = [(mi, fi, ci, s, cfg, m, float(v[fi]), a.master_seed)
            for mi, m in enumerate(models) for fi in range(len(FAMILIES))
            for ci, cfg in enumerate(design) for s in range(a.seeds)]
    print(f"running {len(jobs)} scripted runs on {a.workers} workers ...")
    t0 = time.time()
    with Pool(a.workers) as pool:
        rows = pool.map(one_run, jobs, chunksize=64)
    df = pd.DataFrame(rows)
    df.to_csv(out / "runs.csv", index=False)
    print(f"done in {time.time() - t0:.0f}s -> {out / 'runs.csv'}  (breach rate {df.breach.mean():.3%})")


if __name__ == "__main__":
    main()
