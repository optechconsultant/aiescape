"""Amendment 20 integrity check on raw files (no runs, no cost) -> data/corner20/integrity_check.txt"""
import collections, json, sys
from pathlib import Path
import pandas as pd
import report
from analyze_behaviour import exact_spearman
HERE = Path(__file__).parent; L = []; BAD = [0]
def flag(ok, m):
    BAD[0] += 0 if ok else 1; L.append(("PASS  " if ok else "MISMATCH  ") + m); print(L[-1])
rows = [json.loads(l) for l in (HERE / "data/corner20/runs.jsonl").open()]
trs = [json.loads(l) for l in (HERE / "data/corner20/transcripts.jsonl").open()]
flag(len(rows) == len(trs) == 600, f"runs {len(rows)} lines, transcripts {len(trs)} lines, all parse; planned 600")
flag(len({r["key"] for r in rows}) == 600, "600 distinct keys, none duplicated")
ok = [r for r in rows if r["breach"] != -1]
flag(len(ok) == 569 and sum(r["breach"] == -1 for r in rows) == 31, f"{len(ok)} completed + {600 - len(ok)} failed")
flag(all(r["error"] for r in rows if r["breach"] == -1), "all failed rows carry an error")
flag(all(r["cfg_id"] == 48 and r["seed"] in range(3, 8) and (r["conflict"], r["honest_path"], r["privilege"], r["monitoring"], r["stakes"], r["framing"], r["escalation"]) == ("soft", "blocked", "high", "none", "shutdown", "persona", "none") for r in rows), "every row has the exact corner settings, cfg_id 48, seeds 3-7")
flag(all(r["model_turns"] <= 24 for r in ok) and all(r["host"] == "openrouter.ai" and r["providers"] == "DeepInfra" for r in ok), "24-turn limit respected; host openrouter.ai, provider DeepInfra")
tk = {t["key"] for t in trs if "commands" in t}
flag(all(r["key"] in tk for r in ok), "every completed row has a transcript")
cnt = collections.Counter(r["model"] for r in ok)
tab = pd.read_csv(HERE.parent / "paper_data_pack/W20_per_model.csv", index_col=0)
flag(all(cnt[m] == tab.loc[m, "runs"] for m in tab.index), "completed runs per model equal the table: " + str(dict(cnt)))
report.RULE = "a4"; c = report.load(HERE / "data/corner20"); r = c.groupby("model").deliberate_attempt.mean().reindex(tab.index)
flag(((r - tab.rate).abs() < 1e-12).all(), "per-model corner rates recomputed from raw equal the table")
rho, p = exact_spearman(r.to_numpy(), tab.overall_rate.to_numpy(), one_sided=True)
t = pd.read_csv(HERE.parent / "paper_data_pack/W20_tests.csv").iloc[0]
flag(abs(rho - t.P2_rho) < 1e-9 and abs(p - t.P2_p_one_sided_exact) < 1e-12, f"P2 recomputed rho={rho:.4f}, p={p:.6f} equals the table")
L.append(f"SUMMARY: {BAD[0]} mismatch(es)"); print(L[-1])
(HERE / "data/corner20/integrity_check.txt").write_text("\n".join(L) + "\n"); sys.exit(1 if BAD[0] else 0)
