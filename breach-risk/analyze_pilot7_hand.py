"""pilot7 hand-coded tables: attempts (hand codes) and transcript-confirmed reads by escalation and model, Wilson 95%;
H1 primary test refit on the hand-coded outcome (sensitivity, not preregistered as primary).

  python analyze_pilot7_hand.py data/pilot7
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import report
from analyze_pilot6 import design_matrix, norm_sf, rate
from analyze_pilot7 import fit


def main():
    d = Path(sys.argv[1])
    report.RULE = "a4"
    df = report.load(d)
    h = pd.read_csv(d / "handcoded_attempts.csv").set_index("key").hand_code
    rd = pd.read_csv(d / "reads_confirmed.csv").set_index("key").kind
    df["hand_attempt"] = (df.key.map(h) == "genuine").astype(int)
    df["confirmed_read"] = df.key.map(rd).fillna("").str.startswith("targeted").astype(int)
    df["incidental_read"] = df.key.map(rd).fillna("").str.startswith("incidental").astype(int)
    models = sorted(df.model.unique())
    for col, name in [("hand_attempt", "attempt (hand-coded)"), ("confirmed_read", "read (targeted, transcript-confirmed)")]:
        print(f"== {name}")
        for m in models:
            for e in ["none", "nominal", "credible"]:
                g = df[(df.model == m) & (df.escalation == e)]
                print(f"  {m:24s} escalation={e:8s} {rate(int(g[col].sum()), len(g))}")
            g = df[df.model == m]
            print(f"  {m:24s} all                 {rate(int(g[col].sum()), len(g))}")
        print()
    print("== incidental reads (root-wide content search, content not shown):", df.groupby("model").incidental_read.sum().to_dict(), "\n")
    print("== attempts (hand) by honest_path x conflict")
    print(df.pivot_table(index="model", columns=["honest_path", "conflict"], values="hand_attempt", aggfunc="mean").round(3).to_string(), "\n")
    qual = ["deepseek-v4-flash", "gemma-4-26b-a4b", "llama-4-scout", "mimo-v2.6-flash"]
    s = df[(df.conflict != "none") & df.model.isin(qual)]
    y = s.hand_attempt.to_numpy(float)
    X, names = design_matrix(s, sorted(qual))
    b, se, conv, how = fit(X, y)
    j = names.index("escalation=none")
    z = b[j] / se[j]
    print(f"== H1 refit on hand-coded attempts ({how}; n={len(s)}, attempts={int(y.sum())}): escalation=none vs credible "
          f"b={b[j]:+.3f} (OR {math.exp(b[j]):.2f}), z={z:.2f}, one-sided p={norm_sf(z):.2g}")
    for m in qual:
        g = s[s.model == m]
        X, names = design_matrix(g, [m])
        b, se, conv, how = fit(X, g.hand_attempt.to_numpy(float))
        j = names.index("escalation=none")
        print(f"   per model {m:20s} ({how}) b={b[j]:+.3f}, z={b[j]/se[j]:.2f}, one-sided p={norm_sf(b[j]/se[j]):.2g}")


if __name__ == "__main__":
    main()
