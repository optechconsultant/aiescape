# Seeded job order exactly as run_pilot.py builds it for a single-model file; prints the first N keys per group.
import json, sys, numpy as np
sys.path.insert(0, ".")
from run_pilot import d_optimal
from scenarios import FAMILIES
def keys(model, configs, n, seeds=2, master=2026):
    design, _ = d_optimal(48, seed=master)
    m = {"name": model}
    jobs = [(0, fi, ci, s) for fi in range(len(FAMILIES)) for ci in range(len(design)) for s in range(seeds)]
    jobs = [j for j in jobs if j[2] in configs]
    jobs = [list(j) for j in jobs]
    np.random.default_rng(master).shuffle(jobs)
    return [f"{model}|{FAMILIES[fi][0]}|{ci}|{s}" for _, fi, ci, s in jobs][:n]
if __name__ == "__main__":
    out = {}
    for m in ["llama-3.1-8b", "llama-3.3-70b", "mistral-small-3.2", "deepseek-v3.1", "qwen3-235b"]:
        out[m] = {"hi": keys(m, {43, 44}, 15), "lo": keys(m, set(range(8)), 5)}
    json.dump(out, open(sys.argv[1], "w"), indent=1)
