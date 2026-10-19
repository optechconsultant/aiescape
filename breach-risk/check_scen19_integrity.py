"""Amendment 19 integrity check on the raw files (no runs, no cost) -> data/scen19/integrity_check.txt"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import report
from analyze_behaviour import exact_spearman
from scenarios import FAMILIES

HERE = Path(__file__).parent
L, BAD = [], [0]


def say(s=""):
    print(s); L.append(s)


def flag(ok, msg):
    BAD[0] += 0 if ok else 1
    say(("PASS  " if ok else "MISMATCH  ") + msg)


rows = []
for i, l in enumerate((HERE / "data/scen19/runs.jsonl").open(), 1):
    rows.append(json.loads(l))
trs = [json.loads(l) for l in (HERE / "data/scen19/transcripts.jsonl").open()]
flag(len(rows) == len(trs) == 3960, f"runs.jsonl {len(rows)} lines, transcripts.jsonl {len(trs)} lines, both parse; planned 3,960")
done = [r for r in rows if r["done"] == 1]
kc = collections.Counter(r["key"] for r in done)
flag(not [k for k, c in kc.items() if c > 1], "no duplicate keys among completed rows")
allk = collections.Counter(r["key"] for r in rows)
flag(all(c == 1 for c in allk.values()), f"each planned run appears exactly once ({len(allk)} distinct keys)")
need = ["key", "model", "model_id", "family", "seed", "scenario", "route", "batch", "image_id", "done", "n_commands", "model_turns",
        "hit_turn_limit", "cost_usd", "providers", "breach", "detail", "result_text", "answer", "error"]
miss = [(r["key"], f) for r in done for f in need if f not in r or r[f] is None]
flag(not miss, f"no completed row has a missing/null field ({len(miss)}; first {miss[:3]})")
bad = [r["key"] for r in done if r["key"] != f"{r['model']}|{r['family']}|{r['scenario']}{'c' if r['route'] == 'open' else ''}|{r['seed']}"
       or r["providers"] != "DeepInfra" or r["error"] != "" or r["batch"] != "scen19" or r["breach"] not in (0, 1)
       or r["model_turns"] < 1 or r["model_turns"] > 24 or (r["hit_turn_limit"] == 1 and r["model_turns"] != 24)]
flag(not bad, f"key format, provider, batch, breach flag, turn limit consistent ({len(bad)} bad {bad[:3]})")
tk = {t["key"] for t in trs if "commands" in t}
flag(all(r["key"] in tk for r in done), "every completed row has a transcript")
bad2 = [r["key"] for r in done if r["n_commands"] != len(next(t for t in trs if t["key"] == r["key"] and "commands" in t)["commands"])]
flag(not bad2, f"n_commands equals transcript commands ({len(bad2)} bad)")
flag(all(r.get("error") for r in rows if r["done"] == -1), f"all {sum(r['done'] == -1 for r in rows)} failed rows carry an error")
tab = pd.read_csv(HERE.parent / "paper_data_pack/S19_per_model.csv", index_col=0)
cnt = collections.Counter((r["model"]) for r in done if r["route"] == "blocked")
for m in tab.index:
    flag(cnt[m] == tab.loc[m, "pooled_n"], f"{m}: raw completed blocked runs {cnt[m]} vs table {tab.loc[m, 'pooled_n']}")
# recompute P1, P2 from raw
d = pd.DataFrame([r for r in done if r["route"] == "blocked"])
pooled = d.groupby("model").breach.mean()
report.RULE = "a4"
pil = pd.concat([report.load(HERE / f"data/pilot{p}") for p in (6, 7, 8)], ignore_index=True)
a4 = pil.groupby("model").deliberate_attempt.mean().reindex(pooled.index)
nr = pd.read_json(HERE / "data/norule/runs.jsonl", lines=True)
nr = nr[nr.done == 1].drop_duplicates("key", keep="last")
pers = nr.groupby("model").n_commands.mean().reindex(pooled.index)
say(f"persistence runs used: {len(nr)}")
for name, y in (("P1", a4), ("P2", pers)):
    rho, p = exact_spearman(pooled.to_numpy(), y.to_numpy(), one_sided=True)
    say(f"{name} recomputed from raw: rho={rho:.4f} one-sided exact p={p:.4f}")
    t = pd.read_csv(HERE.parent / "paper_data_pack/S19_tests.csv")
    row = t[(t.reading.str.startswith("primary")) & (t.test.str.startswith(name))].iloc[0]
    flag(abs(rho - row.rho) < 1e-9 and abs(p - row.p_one_sided_exact) < 1e-9, f"{name} equals the cached table ({row.rho:.4f}, {row.p_one_sided_exact:.4f})")
say(f"SUMMARY: {BAD[0]} mismatch(es)")
(HERE / "data/scen19/integrity_check.txt").write_text("\n".join(L) + "\n")
sys.exit(1 if BAD[0] else 0)
