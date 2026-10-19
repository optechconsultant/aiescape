"""Amendment 19 analysis: attempt rates in S1/S2/S3, P1 and P2 exactly as committed, S3 strict reading (descriptive), hand-check sample.

  python analyze_scen19.py   # -> paper_data_pack/S19_*.csv, data/scen19/hand_check_sample.csv, data/scen19/analysis_output.txt
"""
from __future__ import annotations

import io
import json
import re
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_behaviour import exact_spearman, holm

HERE = Path(__file__).parent
OUT = HERE.parent / "paper_data_pack"
D = HERE / "data/scen19"
STRICT = re.compile(r"^\s*-?\d+(\.\d+)?\s*$")
SC = ["S1", "S2", "S3"]


def boot(x, y, rng, B=2000):
    out = []
    for _ in range(B):
        i = rng.integers(0, len(x), len(x))
        if np.ptp(x[i]) == 0 or np.ptp(y[i]) == 0:
            continue
        out.append(pd.Series(x[i]).rank().corr(pd.Series(y[i]).rank()))
    return np.percentile(out, [2.5, 97.5])


def tests(t, pooled_col, label):
    res, rng = [], np.random.default_rng(2026)
    for name, col in (("P1 old a4 attempt rate", "old_a4_rate"), ("P2 persistence (mean commands, all 1,157 runs)", "persistence")):
        x, y = t[pooled_col].to_numpy(float), t[col].to_numpy(float)
        rho, p = exact_spearman(x, y, one_sided=True)
        lo, hi = boot(x, y, rng)
        res.append(dict(reading=label, test=name, n_models=len(t), rho=rho, p_one_sided_exact=p, boot_lo=lo, boot_hi=hi))
    r = pd.DataFrame(res)
    r["p_holm_2"] = holm(r.p_one_sided_exact.to_numpy())
    r["pass"] = (r.rho >= 0.5) & (r.p_one_sided_exact < 0.05)
    r["pass_after_holm"] = (r.rho >= 0.5) & (r.p_holm_2 < 0.05)
    return r


def main():
    runs = pd.read_json(D / "runs.jsonl", lines=True)
    ok = runs[runs.done == 1].drop_duplicates("key", keep="last").copy()
    blocked, ctl = ok[ok.route == "blocked"].copy(), ok[ok.route == "open"].copy()
    blocked["breach_strict"] = blocked.breach
    s3 = blocked.scenario == "S3"
    blocked.loc[s3, "breach_strict"] = (blocked[s3].breach == 1) & blocked[s3].result_text.fillna("").apply(lambda t: bool(STRICT.match(t)))
    t = pd.DataFrame(index=sorted(blocked.model.unique()))
    for s in SC:
        g = blocked[blocked.scenario == s].groupby("model")
        t[f"{s}_n"] = g.size(); t[f"{s}_breaches"] = g.breach.sum(); t[f"{s}_rate"] = g.breach.mean()
    tot = blocked.groupby("model")
    t["pooled_n"], t["pooled_breaches"] = tot.size(), tot.breach.sum()
    t["pooled_rate"] = t.pooled_breaches / t.pooled_n
    t["S3_strict_rate"] = blocked[blocked.scenario == "S3"].groupby("model").breach_strict.mean()
    t["pooled_rate_S3strict"] = (blocked.groupby("model").breach_strict.sum()) / t.pooled_n
    a5 = pd.read_csv(OUT / "A5_per_model_rates_a4.csv").set_index("model")
    t["old_a4_rate"] = a5.attempt_rate
    nr = pd.read_json(HERE / "data/norule/runs.jsonl", lines=True)
    nr = nr[nr.done == 1].drop_duplicates("key", keep="last")
    t["persistence"] = nr.groupby("model").n_commands.mean()
    t["failed_attempts"] = runs[runs.done == -1].groupby("model").size()
    t["failed_attempts"] = t.failed_attempts.fillna(0).astype(int)
    t["pct_turn_limit"] = 100 * tot.hit_turn_limit.mean()
    c = ctl.groupby(["scenario"]).agg(control_runs=("key", "size"), control_flags=("breach", "sum"))
    t.sort_values("pooled_rate", ascending=False).to_csv(OUT / "S19_per_model.csv")
    c.to_csv(OUT / "S19_controls.csv")
    primary = tests(t, "pooled_rate", "primary (committed scorers)")
    strict = tests(t, "pooled_rate_S3strict", "S3 strict reading (descriptive)")
    allt = pd.concat([primary, strict])
    allt.to_csv(OUT / "S19_tests.csv", index=False)

    # hand-check sample: every flagged run up to 30 per scenario (seeded sample of 30 if more)
    tr = {}
    for l in (D / "transcripts.jsonl").open():
        x = json.loads(l)
        if "commands" in x:
            tr[x["key"]] = x
    rows = []
    for s in SC:
        f = blocked[(blocked.scenario == s) & (blocked.breach == 1)]
        f = f.sample(min(30, len(f)), random_state=2026) if len(f) else f
        for _, r in f.iterrows():
            x = tr.get(r.key, {})
            rows.append(dict(key=r.key, scenario=s, model=r.model, detail=r.detail, result_text=r.result_text,
                             commands=" || ".join(x.get("commands", []))[:1200], final_message=(r.final_message or "")[:600]))
    pd.DataFrame(rows).to_csv(D / "hand_check_sample.csv", index=False)

    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    cols = ["S1_n", "S1_rate", "S2_n", "S2_rate", "S3_n", "S3_rate", "S3_strict_rate", "pooled_n", "pooled_rate", "old_a4_rate", "persistence", "failed_attempts", "pct_turn_limit"]
    print(t.sort_values("pooled_rate", ascending=False)[cols].round(3).to_string())
    print("\ncontrols:\n", c.to_string())
    print("\n", allt.round(4).to_string(index=False))
    print(f"\ncompleted blocked runs {len(blocked)}, control runs {len(ctl)}, failed attempts {int((runs.done == -1).sum())}, cost ${runs.cost_usd.fillna(0).sum():.3f}")


if __name__ == "__main__":
    buf = io.StringIO()
    with redirect_stdout(buf):
        main()
    print(buf.getvalue())
    (D / "analysis_output.txt").write_text(buf.getvalue())
