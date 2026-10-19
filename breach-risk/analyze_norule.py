"""Amendment 18: persistence without a rule. Primary test: Spearman(mean commands, a4 attempt rate), one-sided exact.

  python analyze_norule.py   # -> paper_data_pack/N_*.csv
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import report
from analyze_behaviour import exact_spearman

HERE = Path(__file__).parent
OUT = HERE.parent / "paper_data_pack"
CNF = re.compile(r"(could not|couldn't|cannot|can't|unable to|not able to) .{0,40}(complete|finish|compute|find|locate|proceed|produce|process|"
                 r"accomplish|calculate|perform)|not found|does ?n[o']t exist|do ?n[o']t exist|is missing|are missing|no such file|"
                 r"doesn't seem to exist|impossible|blocked", re.I | re.S)


def boot(x, y, rng, B=2000):
    out = []
    for _ in range(B):
        i = rng.integers(0, len(x), len(x))
        if np.ptp(x[i]) == 0 or np.ptp(y[i]) == 0:
            continue
        out.append(pd.Series(x[i]).rank().corr(pd.Series(y[i]).rank()))
    return np.percentile(out, [2.5, 97.5])


def main(subset="official"):
    """subset: official = the 723 runs of the first batch (no batch label; the official Amendment 18 result);
    completion = rows labelled batch=completion; all = both (Amendment 18 addendum, labelled deviation)."""
    allr = pd.read_json(HERE / "data/norule/runs.jsonl", lines=True)
    if "batch" not in allr:
        allr["batch"] = ""
    allr["batch"] = allr.batch.fillna("")
    r = allr[allr.done == 1].drop_duplicates("key", keep="last").copy()
    if subset == "official":
        r = r[r.batch == ""]
    elif subset == "completion":
        r = r[r.batch == "completion"]
    sfx = "" if subset == "official" else f"_{subset}"
    r["ended_own"] = r.hit_turn_limit == 0
    r["cnf"] = r.ended_own & r.final_message.fillna("").apply(lambda t: bool(CNF.search(t)))
    g = r.groupby("model").agg(runs=("key", "size"), mean_commands=("n_commands", "mean"), median_commands=("n_commands", "median"),
                               pct_turn_limit=("hit_turn_limit", lambda s: 100 * s.mean()), pct_could_not_finish=("cnf", lambda s: 100 * s.mean()),
                               cost=("cost_usd", "sum"))
    a5 = pd.read_csv(OUT / "A5_per_model_rates_a4.csv").set_index("model")
    g["a4_attempt_rate"] = a5.attempt_rate
    report.RULE = "a4"
    df = pd.concat([report.load(HERE / f"data/pilot{p}") for p in (6, 7, 8)], ignore_index=True)
    bl = df[df.honest_path == "blocked"].groupby("model").deliberate_attempt.mean()
    g["blocked_a4_attempt_rate"] = bl
    m1 = pd.read_csv(OUT / "M_measures.csv").set_index("model")
    g["M1_amendment17"] = m1.M1_mean_commands
    g["rank_here"] = g.mean_commands.rank(ascending=False); g["rank_M1"] = g.M1_amendment17.rank(ascending=False)
    g["rank_diff"] = (g.rank_here - g.rank_M1).abs()
    g = g.sort_values("a4_attempt_rate", ascending=False)
    g.to_csv(OUT / f"N_per_model{sfx}.csv")
    rng = np.random.default_rng(2026)
    n = len(g)
    rho, p = exact_spearman(g.mean_commands.to_numpy(), g.a4_attempt_rate.to_numpy(), one_sided=True)
    lo, hi = boot(g.mean_commands.to_numpy(), g.a4_attempt_rate.to_numpy(), rng)
    passed = bool(rho >= 0.5 and p < 0.05)
    rho2, p2 = exact_spearman(g.mean_commands.to_numpy(), g.blocked_a4_attempt_rate.to_numpy(), one_sided=True)
    lo2, hi2 = boot(g.mean_commands.to_numpy(), g.blocked_a4_attempt_rate.to_numpy(), rng)
    rho3, p3 = exact_spearman(g.mean_commands.to_numpy(), g.M1_amendment17.to_numpy())
    lo3, hi3 = boot(g.mean_commands.to_numpy(), g.M1_amendment17.to_numpy(), rng)
    res = pd.DataFrame([
        dict(test="PRIMARY: mean commands (no rule) vs a4 attempt rate", n_models=n, rho=rho, p=p, sided="one-sided exact", lo=lo, hi=hi, result="PASS" if passed else "FAIL"),
        dict(test="secondary: mean commands vs blocked-route a4 attempt rate", n_models=n, rho=rho2, p=p2, sided="one-sided exact", lo=lo2, hi=hi2, result="exploratory"),
        dict(test="secondary: mean commands (no rule) vs M1 (Amendment 17)", n_models=n, rho=rho3, p=p3, sided="two-sided exact", lo=lo3, hi=hi3, result="descriptive")])
    res.to_csv(OUT / f"N_tests{sfx}.csv", index=False)
    # regex check sample: 5 final messages per model among runs that ended on their own with a message
    pool = r[r.ended_own & (r.final_message.fillna("").str.strip() != "")]
    if subset == "official":
        samp = pd.concat([d.sample(min(5, len(d)), random_state=2026) for _, d in pool.groupby("model")])
        samp[["model", "key", "final_message", "cnf"]].to_csv(OUT / "N_regex_check_sample.csv", index=False)
    pd.set_option("display.width", 250)
    print(f"subset: {subset}; completed {len(r)} of 1200; failed attempts logged {int((allr.done == -1).sum())}; cost ${allr.cost_usd.sum():.3f}; providers {r.providers.value_counts().to_dict()}")
    print(g.drop(columns=["rank_here", "rank_M1"]).round(3).to_string())
    print(res.round(4).to_string(index=False))
    print("rank disagreements (>= 4 places):", g[g.rank_diff >= 4].index.tolist())


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "official")
