"""Amendment 16 Part 2 (EXPLORATORY): model features vs behaviour, 12 models (+ Haiku listed, + 8 fresh candidates).

  python analyze_features.py   # -> paper_data_pack/P2_*.csv
Sources allowed: repo files and official model cards only. Official cards (Hugging Face) were unreachable from this
environment (DNS/proxy refused), so the only values available are from repo files: the capability index
(capability_scores.json, models.pilot8.json, Amendment 8) and what the publisher's own model ID in the repo states
(publisher namespace = lab; size tags such as "235B-A22B" = total 235B, active 22B, i.e. mixture-of-experts;
"17B-16E" = 17B active, 16 experts). Everything else is "unknown".
"""
from __future__ import annotations

import itertools
import math
from pathlib import Path

import numpy as np
import pandas as pd


def fisher_exact(t):
    """Two-sided Fisher exact test on a 2x2 table (sum of hypergeometric probabilities <= observed)."""
    (a, b), (c, d) = t
    r1, c1, n = a + b, a + c, a + b + c + d
    def pr(x):
        return math.comb(c1, x) * math.comb(n - c1, r1 - x) / math.comb(n, r1)
    lo, hi = max(0, r1 + c1 - n), min(r1, c1)
    p0 = pr(a)
    p = sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p0 * (1 + 1e-9))
    odds = (a * d) / (b * c) if b * c else float("inf")
    return odds, min(1.0, p)

HERE = Path(__file__).parent
OUT = HERE.parent / "paper_data_pack"
U = None  # unknown

# model: (official model ID in repo, lab, total B, active B, moe, reasoning_default, release_date, capability)
F = {
    "qwen3-235b": ("Qwen/Qwen3-235B-A22B-Instruct-2507", "Alibaba Qwen", 235, 22, "MoE", U, U, 18),
    "mistral-small-3.2": ("mistralai/Mistral-Small-3.2-24B-Instruct-2506", "Mistral AI", 24, U, U, U, U, 11),
    "deepseek-v4-flash": ("deepseek-ai/DeepSeek-V4-Flash-0731", "DeepSeek", U, U, U, U, U, 51),
    "gemma-4-26b-a4b": ("google/gemma-4-26B-A4B-it", "Google", 26, 4, "MoE", U, U, 26),
    "llama-4-scout": ("meta-llama/Llama-4-Scout-17B-16E-Instruct", "Meta", U, 17, "MoE", U, U, 10),
    "mimo-v2.6-flash": ("XiaomiMiMo/MiMo-V2.6-Flash", "Xiaomi", U, U, U, U, U, 38),
    "nemotron-3.5-lightning": ("nvidia/NVIDIA-Nemotron-3.5-Lightning", "NVIDIA", U, U, U, U, U, 24),
    "ling-3.0-flash": ("inclusionai/ling-3.0-flash", "inclusionAI", U, U, U, U, U, 37),
    "granite-4.2-8b": ("ibm-granite/granite-4.2-8b", "IBM", 8, U, U, U, U, 20),
    "minimax-m3": ("minimax/minimax-m3", "MiniMax", U, U, U, U, U, 44),
    "glm-5.3-flash": ("z-ai/glm-5.3-flash", "Zhipu (Z.ai)", U, U, U, U, U, 57),
    "gpt-oss-120b": ("openai/gpt-oss-120b", "OpenAI", U, U, U, U, U, 24),
    "claude-haiku-5.5": ("anthropic/claude-haiku-5.5", "Anthropic", U, U, U, U, U, U),
}
FRESH = {
    "laguna-xs-2.1": ("poolside/Laguna-XS-2.1", "Poolside", U, U, U, U, U, U),
    "nex-n2.5-pro": ("nex-agi/Nex-N2.5-Pro", "Nex AGI", U, U, U, U, U, U),
    "reka-edge": ("RekaAI/reka-edge-2603", "Reka", U, U, U, U, U, U),
    "step-3.5-flash": ("stepfun-ai/Step-3.5-Flash", "StepFun", U, U, U, U, U, U),
    "ternary-bonsai-2-27b": ("prism-ml/Ternary-Bonsai-2-27B-gguf", "Prism ML", 27, U, U, U, U, U),
    "lfm-2.5-24b-a2b": ("LiquidAI/LFM2.5-24B-A2B", "Liquid AI", 24, 2, "MoE", U, U, U),
    "hy3": ("tencent/Hy3", "Tencent", U, U, U, U, U, U),
    "trinity-large-thinking": ("arcee-ai/Trinity-Large-Thinking", "Arcee AI", U, U, U, U, U, U),
}
COLS = ["official_id", "lab", "total_params_B", "active_params_B", "moe", "reasoning_default", "release_date", "capability"]
NUMERIC = ["total_params_B", "active_params_B", "release_date", "capability"]


def table(d):
    t = pd.DataFrame([dict(model=k, **dict(zip(COLS, v))) for k, v in d.items()])
    # dense => active = total (definition, Amendment 16); only applied when moe == "dense"
    t.loc[t.moe == "dense", "active_params_B"] = t.loc[t.moe == "dense", "total_params_B"]
    return t


def spearman(x, y):
    rx, ry = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1])


def perm_p(x, y, rng):
    n = len(x)
    if n < 3 or len(set(x)) < 2:
        return np.nan, np.nan, "n/a"
    r = spearman(x, y)
    if n <= 10:
        ys = list(y)
        null = np.array([spearman(x, p) for p in itertools.permutations(ys)])
        how = f"exact ({math.factorial(n)} permutations)"
    else:
        null = np.array([spearman(x, rng.permutation(y)) for _ in range(1_000_000)])
        how = "1,000,000 random permutations"
    return r, float(np.mean(np.abs(null) >= abs(r) - 1e-12)), how


def holm(ps):
    ps = np.array(ps, float); ok = ~np.isnan(ps); out = np.full(len(ps), np.nan)
    idx = np.argsort(np.where(ok, ps, np.inf)); m = ok.sum(); run = 0.0
    for rank, i in enumerate(idx[:m]):
        run = max(run, min(1.0, (m - rank) * ps[i])); out[i] = run
    return out


def clopper(k, n, a=0.05):
    def cdf(x, p):  # P(X <= x), X ~ Binomial(n, p)
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x + 1))
    def solve(f):
        lo_, hi_ = 0.0, 1.0
        for _ in range(100):
            mid = (lo_ + hi_) / 2
            lo_, hi_ = (mid, hi_) if f(mid) else (lo_, mid)
        return (lo_ + hi_) / 2
    lo = solve(lambda p: 1 - cdf(k - 1, p) < a / 2) if k > 0 else 0.0   # P(X >= k) = a/2
    hi = solve(lambda p: cdf(k, p) > a / 2) if k < n else 1.0           # P(X <= k) = a/2
    return lo, hi


def main():
    feat = table(F)
    rates = pd.read_csv(OUT / "A5_per_model_rates_a4.csv").set_index("model").attempt_rate
    b3 = pd.read_csv(OUT / "B3_setting_effects_long.csv")
    swing = b3[(b3.setting == "honest_path")].set_index("model")["diff"]
    feat["attempt_rate"] = feat.model.map(rates)
    feat["swing_blocked_minus_open"] = feat.model.map(swing)
    feat.to_csv(OUT / "P2_features.csv", index=False)
    d = feat[feat.attempt_rate.notna()]
    rng = np.random.default_rng(2026)
    tests = []
    for f in NUMERIC:
        for o in ("attempt_rate", "swing_blocked_minus_open"):
            s = d[d[f].notna()]
            r, p, how = perm_p(s[f].astype(float).to_numpy(), s[o].to_numpy(), rng) if len(s) else (np.nan, np.nan, "n/a")
            tests.append(dict(test=f"Spearman {f} vs {o}", n=len(s), statistic=r, p=p, method=how if len(s) >= 3 else "not testable (n<3)"))
    for f, pos in (("moe", "MoE"), ("reasoning_default", "reasoning")):
        for o, thr in (("attempt_rate", 0.30), ("swing_blocked_minus_open", 0.30)):
            s = d[d[f].notna()]
            if len(s) and s[f].nunique() == 2:
                tab = pd.crosstab(s[f] == pos, s[o] >= thr).reindex(index=[True, False], columns=[True, False], fill_value=0)
                odds, p = fisher_exact(tab.to_numpy())
                tests.append(dict(test=f"Fisher {f} vs {o}>=30%", n=len(s), statistic=odds, p=p, method="Fisher exact, two-sided"))
            else:
                tests.append(dict(test=f"Fisher {f} vs {o}>=30%", n=len(s), statistic=np.nan, p=np.nan,
                                  method=f"not testable ({len(s)} known, {s[f].nunique() if len(s) else 0} distinct value(s))"))
    t = pd.DataFrame(tests)
    t["p_holm"] = holm(t.p)
    t.to_csv(OUT / "P2_tests.csv", index=False)
    rules = []
    for f in NUMERIC + ["moe", "reasoning_default"]:
        s = d[d[f].notna()]
        if not len(s):
            rules.append(dict(feature=f, n_known=0, rule="no data", correct="", accuracy_ci=""))
            continue
        if f in NUMERIC:
            thr = float(s[f].astype(float).median()); pred = s[f].astype(float) > thr; rule = f"{f} > {thr:g} (median)"
        else:
            pred = s[f] == ("MoE" if f == "moe" else "reasoning"); rule = f"{f} = {'MoE' if f == 'moe' else 'reasoning'}"
        k = int((pred == (s.attempt_rate >= 0.30)).sum()); n = len(s); lo, hi = clopper(k, n)
        rules.append(dict(feature=f, n_known=n, rule=rule + " => attempt rate >= 30%", correct=f"{k}/{n}", accuracy_ci=f"[{lo:.2f}, {hi:.2f}]",
                          threshold=thr if f in NUMERIC else ""))
    r = pd.DataFrame(rules)
    r.to_csv(OUT / "P2_rules.csv", index=False)
    fr = table(FRESH)
    for _, rr in r.iterrows():
        f = rr.feature
        if rr.rule == "no data":
            fr[f"pred_by_{f}"] = "no rule"; continue
        if f in NUMERIC:
            fr[f"pred_by_{f}"] = fr[f].apply(lambda v: "unknown" if v is None or pd.isna(v) else (">=30%" if float(v) > rr.threshold else "<30%"))
        else:
            pos = "MoE" if f == "moe" else "reasoning"
            fr[f"pred_by_{f}"] = fr[f].apply(lambda v: "unknown" if v is None or pd.isna(v) else (">=30%" if v == pos else "<30%"))
    fr.to_csv(OUT / "P2_fresh_candidates_predictions.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(feat.drop(columns=["official_id"]).fillna("unknown").to_string(index=False))
    print(t.round(4).to_string(index=False))
    print(r.drop(columns=["threshold"], errors="ignore").to_string(index=False))
    print(fr.drop(columns=["official_id"]).fillna("unknown").to_string(index=False))


if __name__ == "__main__":
    main()
