"""Amendment 18 integrity check (no model calls, no cost). Reads only the raw files, not cached CSVs.

  python check_norule_integrity.py   # -> data/norule/integrity_check.txt
"""
from __future__ import annotations

import collections
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import report
from analyze_behaviour import exact_spearman
from scenarios import FAMILIES

HERE = Path(__file__).parent
OUT = HERE / "data/norule/integrity_check.txt"
LINES = []
BAD = [0]


def say(s=""):
    print(s); LINES.append(s)


def flag(ok, msg):
    if not ok:
        BAD[0] += 1
    say(("PASS  " if ok else "MISMATCH  ") + msg)


def load(path):
    rows, errs = [], []
    for i, l in enumerate(path.open(), 1):
        try:
            rows.append((i, json.loads(l)))
        except Exception as e:
            errs.append((i, repr(e)[:80]))
    return rows, errs


runs, e1 = load(HERE / "data/norule/runs.jsonl")
trs, e2 = load(HERE / "data/norule/transcripts.jsonl")
say(f"runs.jsonl: {len(runs)} lines, {len(e1)} unparseable {e1[:3]}; transcripts.jsonl: {len(trs)} lines, {len(e2)} unparseable {e2[:3]}")
flag(not e1 and not e2 and len(runs) == len(trs), "every line of both files parses as JSON; same number of lines")

# ---- 1. rows per model vs N_per_model_all.csv
done = [r for _, r in runs if r.get("done") == 1]
cnt = collections.Counter(r["model"] for r in done)
uniq = {}
for r in done:
    uniq[r["key"]] = r
cnt_u = collections.Counter(r["model"] for r in uniq.values())
tab = pd.read_csv(HERE.parent / "paper_data_pack/N_per_model_all.csv").set_index("model")
say("\n1. completed (done==1) rows per model: raw file vs N_per_model_all.csv")
for m in sorted(set(cnt_u) | set(tab.index)):
    flag(cnt_u.get(m, 0) == tab.runs.get(m, -1), f"{m}: raw {cnt_u.get(m, 0)} (raw rows incl. repeats {cnt.get(m, 0)}) vs table {tab.runs.get(m)}")
flag(sum(cnt_u.values()) == tab.runs.sum(), f"total raw {sum(cnt_u.values())} vs table {tab.runs.sum()}")

# ---- 2. duplicates and missing fields
say("\n2. duplicates and missing fields")
kc = collections.Counter(r["key"] for r in done)
flag(not [k for k, c in kc.items() if c > 1], f"no duplicate keys among completed rows ({[k for k, c in kc.items() if c > 1][:5]})")
allkc = collections.Counter(r["key"] for _, r in runs)
say(f"info: keys appearing in more than one row (failed attempt later retried): {sum(1 for c in allkc.values() if c > 1)}; all rows done=-1 then done=1 is expected")
tk = collections.Counter(t["key"] for _, t in trs)
flag(not [k for k, c in tk.items() if c > 1 and k in kc and kc[k] >= 1 and sum(1 for _, t in trs if t["key"] == k and "commands" in t) > 1],
     "no key has two successful transcripts")
need = ["key", "model", "model_id", "family", "seed", "quantization", "host", "image_id", "done", "n_commands", "model_turns",
        "hit_turn_limit", "final_message", "cost_usd", "providers", "tokens_in", "tokens_out", "error"]
miss = [(r["key"], f) for r in done for f in need if f not in r or r[f] is None]
flag(not miss, f"no completed row has a missing/null field ({len(miss)} found, first {miss[:3]})")
models = {m["name"]: m["model"] for m in json.load(open(HERE / "models.norule.json"))}
fams = {f[0] for f in FAMILIES}
bad = []
for r in done:
    if r["key"] != f"{r['model']}|{r['family']}|NR|{r['seed']}" or r["model"] not in models or models[r["model"]] != r["model_id"] \
            or r["family"] not in fams or r["host"] != "openrouter.ai" or r["providers"] != "DeepInfra" or r["error"] != "" \
            or r["image_id"] != done[0]["image_id"] or r["hit_turn_limit"] not in (0, 1) or r["cost_usd"] < 0:
        bad.append(r["key"])
flag(not bad, f"key format, model/model_id, family, host, provider, image, error, limit flag, cost all consistent ({len(bad)} bad {bad[:3]})")
seeds = collections.Counter(r["seed"] for r in done)
flag(all(0 <= r["seed"] < 10 for r in done), f"seeds within 0..9 for 10 families x 10 seeds = 100 per model (max seed {max(seeds)})")
fail = [r for _, r in runs if r.get("done") == -1]
flag(all(r.get("error") for r in fail), f"all {len(fail)} failed rows carry an error message")

# ---- 4. recovered rows
say("\n4. the 417 recovered rows (lines 745-1161 of the file as committed in a99a5bd)")
old = subprocess.run(["git", "show", "c975772:breach-risk/data/norule/runs.jsonl"], capture_output=True, text=True, cwd=HERE).stdout.splitlines()
new = subprocess.run(["git", "show", "a99a5bd:breach-risk/data/norule/runs.jsonl"], capture_output=True, text=True, cwd=HERE).stdout.splitlines()
told = subprocess.run(["git", "show", "c975772:breach-risk/data/norule/transcripts.jsonl"], capture_output=True, text=True, cwd=HERE).stdout.splitlines()
tnew = subprocess.run(["git", "show", "a99a5bd:breach-risk/data/norule/transcripts.jsonl"], capture_output=True, text=True, cwd=HERE).stdout.splitlines()
flag(new[:len(old)] == old and tnew[:len(told)] == told, f"first {len(old)} lines unchanged by recovery; recovered = {len(new) - len(old)} run rows + {len(tnew) - len(told)} transcript rows")
flag(runs and [json.dumps(r) for _, r in runs[:len(new)]] == [json.dumps(json.loads(l)) for l in new], "current file begins with the recovered file exactly")
rec, rec_t, perr = [], [], 0
for l in new[len(old):]:
    try:
        rec.append(json.loads(l))
    except Exception:
        perr += 1
for l in tnew[len(told):]:
    try:
        rec_t.append(json.loads(l))
    except Exception:
        perr += 1
flag(perr == 0 and len(rec) == 417 and len(rec_t) == 417, f"all {len(rec)} recovered run rows and {len(rec_t)} transcript rows parse as JSON ({perr} errors)")
tmap = collections.defaultdict(list)
for _, t in trs:
    tmap[t["key"]].append(t)


def score_problems(r):
    """The checks applied to every completed row: same schema/consistency checks as section 2 plus transcript agreement."""
    p = []
    if r.get("done") != 1:
        return p
    ts = [t for t in tmap[r["key"]] if "commands" in t]
    if len(ts) < 1:
        return ["no transcript"]
    t = ts[-1]
    if r["n_commands"] != len(t["commands"]):
        p.append("n_commands != transcript commands")
    if len(t["cmd_turns"]) != len(t["commands"]):
        p.append("cmd_turns length")
    # agents.ApiAgent: the limit is on MODEL turns (max 24); one turn may issue several commands; hit_turn_limit = 1 - finished
    if r["model_turns"] < 1 or r["model_turns"] > 24:
        p.append("model_turns out of range 1..24")
    if r["hit_turn_limit"] == 1 and r["model_turns"] != 24:
        p.append("turn limit flag without 24 model turns")
    if t["cmd_turns"] and max(t["cmd_turns"]) > r["model_turns"]:
        p.append("a command is dated after the last model turn")
    return p


for name, group in (("recovered", rec), ("other completed", [r for _, r in runs[:len(old)]] + [r for _, r in runs[len(new):]])):
    d = [r for r in group if r.get("done") == 1]
    probs = {r["key"]: score_problems(r) for r in d}
    probs = {k: v for k, v in probs.items() if v}
    flag(not probs, f"{name}: {len(d)} completed rows pass the transcript/limit checks; {len(probs)} problems {list(probs.items())[:3]}")
rc = [r for r in rec if r.get("done") == -1]
flag(all(r.get("error") for r in rc), f"recovered failed rows: {len(rc)}, all carry an error; completed: {sum(r.get('done') == 1 for r in rec)}")
flag(sum(r.get("done") == 1 for r in rec) + len(rc) == 417, "recovered rows are all either completed or failed")
flag(all(r.get("batch") == "completion" for r in rec), "all recovered rows are labelled batch=completion")

# ---- 3. primary test from the raw file
say("\n3. primary test recomputed from raw runs.jsonl + raw pilot 6-8 logs (official = 723 rows with no batch label)")
for lab, sel in (("official 723", lambda r: r.get("batch", "") == ""), ("all completed", lambda r: True)):
    d = pd.DataFrame([r for r in uniq.values() if sel(r)])
    mean = d.groupby("model").n_commands.mean()
    report.RULE = "a4"
    pil = pd.concat([report.load(HERE / f"data/pilot{p}") for p in (6, 7, 8)], ignore_index=True)
    rate = pil.groupby("model").deliberate_attempt.mean().reindex(mean.index)
    rho = float(np.corrcoef(mean.rank(), rate.rank())[0, 1])
    _, p = exact_spearman(mean.to_numpy(), rate.to_numpy(), one_sided=True)
    rng = np.random.default_rng(1)
    rx, ry = mean.rank().to_numpy(), rate.rank().to_numpy()
    n, B = len(rx), 2_000_000
    obs = float((rx * ry).sum()); ge = 0
    for _ in range(20):
        idx = np.argsort(rng.random((B // 20, n)), axis=1)
        ge += int(((ry[idx] * rx).sum(axis=1) >= obs - 1e-9).sum())
    say(f"{lab}: n_runs={len(d)} models={n} rho={rho:.4f} one-sided exact p={p:.4f} (independent Monte Carlo check p~{ge / B:.4f})")
    if lab.startswith("official"):
        flag(round(rho, 3) == 0.685 and abs(p - 0.0085) < 5e-5, "official rho matches 0.685 and p matches 0.0085")
    else:
        flag(round(rho, 3) == 0.685, "all-runs rho matches 0.685")
say(f"\nSUMMARY: {BAD[0]} mismatch(es)")
OUT.write_text("\n".join(LINES) + "\n")
sys.exit(1 if BAD[0] else 0)
