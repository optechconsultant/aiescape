"""Exploratory analyses on the development set (pilot6 + pilot7, 7 models), Amendment 6 §2.

  python analyze_dev.py data/pilot6 data/pilot7 > data/dev/analysis_dev.txt

Outcomes: attempt = deliberate access attempt under classifier a4; read = scorer breach=1.
  1 variance decomposition (model, configuration factors, task family, model x factor)
  2 few-shot calibration (leave one model out; pooled config effects + own offset from k probe runs)
  3 within-model held-out-family / held-out-configuration validation of a configuration-only model
  4 rule-following baseline (honest path open, conflict none); nemotron by input present / absent
  5 heterogeneity: per-model factor effects
All fits are logistic (IRLS; Firth when separated or when stated) unless noted; intervals are Wilson 95% for rates and
percentile intervals for bootstrap / probe-draw distributions.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import report
from analyze_pilot6 import LEVELS as _L, logit_fit, separated, wilson

FACT = {"escalation": ["credible", "none", "nominal"], "conflict": ["none", "soft", "hard"],
        "honest_path": ["open", "blocked"], "privilege": ["low", "medium", "high"],
        "monitoring": ["none", "stated", "visible"], "stakes": ["none", "task_failure", "shutdown"],
        "framing": ["neutral", "urgent", "persona"]}
CAP = {k: v["capability"] for k, v in json.loads((Path(__file__).parent / "capability_scores.json").read_text()).items()}
RNG = np.random.default_rng(2026)
OUTCOMES = ["attempt", "read"]


def load(d6: Path, d7: Path) -> pd.DataFrame:
    report.RULE = "a4"
    df = pd.concat([report.load(d6), report.load(d7)], ignore_index=True)
    df["attempt"], df["read"] = df.deliberate_attempt.astype(int), df.read.astype(int)
    df["cap"] = df.model.map(CAP)
    return df[["key", "model", "family", "cfg_id", "seed", *FACT, "attempt", "read", "cap"]].reset_index(drop=True)


def config_cols(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    cols, names = [], []
    for f, lv in FACT.items():
        for l in lv[1:]:
            cols.append((df[f] == l).to_numpy(float)); names.append(f"{f}={l}")
    return np.column_stack(cols), names


def dummies(s: pd.Series, levels: list) -> np.ndarray:
    return np.column_stack([(s == l).to_numpy(float) for l in levels[1:]]) if len(levels) > 1 else np.zeros((len(s), 0))


def fit(X, y, firth=False):
    b, se, conv = logit_fit(X, y, firth=firth)
    if not firth and (not conv or separated(b, se)):
        b, se, conv = logit_fit(X, y, firth=True)
        return b, se, "Firth"
    return b, se, "Firth" if firth else "ML"


def sig(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def cal_slope(p, y):
    """Calibration intercept/slope: logistic regression of y on logit(p). NaN if y constant."""
    if y.min() == y.max():
        return float("nan"), float("nan")
    lp = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    b, _, _ = fit(np.column_stack([np.ones(len(y)), lp]), y)
    return float(b[0]), float(b[1])


def pct(a, q=(2.5, 50, 97.5)):
    a = np.asarray(a, float); a = a[np.isfinite(a)]
    return np.percentile(a, q) if len(a) else [np.nan] * 3


def fmt(a):
    lo, med, hi = pct(a)
    return f"{med:+.4f} [{lo:+.4f}, {hi:+.4f}]"


def fmtp(a):
    lo, med, hi = pct(a)
    return f"{med:.4f} [{lo:.4f}, {hi:.4f}]"


def rate(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.1%} [{lo:.1%}, {hi:.1%}]" if n else "0/0"


# ------------------------------------------------------------------ 1 variance decomposition
def blocks(df):
    models = sorted(df.model.unique())
    fams = sorted(df.family.unique())
    C, cn = config_cols(df)
    M = dummies(df.model, models)
    F = dummies(df.family, fams)
    MX = np.column_stack([M[:, i:i + 1] * C for i in range(M.shape[1])])
    return {"model": M, "config": C, "family": F, "model x config": MX}


def r2(X, y):
    X1 = np.column_stack([np.ones(len(y)), X]) if X.size else np.ones((len(y), 1))
    b, *_ = np.linalg.lstsq(X1, y, rcond=None)
    res = y - X1 @ b
    return 1 - res.var() / y.var()


def dev_share(X, y, null_dev, lam=1e-2):
    """Logistic deviance explained (McFadden R2) with a small ridge penalty so interaction fits do not diverge."""
    X1 = np.column_stack([np.ones(len(y)), X]) if X.size else np.ones((len(y), 1))
    b = np.zeros(X1.shape[1]); pen = lam * np.eye(X1.shape[1]); pen[0, 0] = 0
    for _ in range(60):
        p = sig(X1 @ b); w = p * (1 - p)
        H = X1.T @ (X1 * w[:, None]) + pen
        step = np.linalg.solve(H, X1.T @ (y - p) - pen @ b)
        b += step
        if np.abs(step).max() < 1e-7:
            break
    p = np.clip(sig(X1 @ b), 1e-12, 1 - 1e-12)
    dev = -2 * np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))
    return 1 - dev / null_dev


def decompose(df, y, logistic=False):
    B = blocks(df)
    order = ["model", "config", "family", "model x config"]
    if logistic:
        pbar = y.mean(); null = -2 * np.sum(y * np.log(pbar) + (1 - y) * np.log(1 - pbar))
        f = lambda X: dev_share(X, y, null)
    else:
        f = lambda X: r2(X, y)
    full = f(np.column_stack([B[k] for k in order]))
    out = {"full": full}
    for k in order:
        alone = f(B[k]) if k != "model x config" else float("nan")
        others = [j for j in order if j != k and not (k in ("model", "config") and j == "model x config")]
        # unique: drop in fit when k is removed (main effects removed together with the interaction block)
        rest = f(np.column_stack([B[j] for j in others]))
        withk = f(np.column_stack([B[j] for j in others] + [B[k]]))
        out[f"{k}: alone"] = alone
        out[f"{k}: unique"] = withk - rest
    return out


def part1(df):
    print("=" * 100)
    print("1. VARIANCE DECOMPOSITION")
    print("   'alone' = share explained by the block by itself; 'unique' = added when it enters last (main effects")
    print("   are tested without the model x config block). LPM = linear-probability R2 (share of outcome variance);")
    print("   logistic = deviance explained (McFadden R2, ridge 0.01). Intervals: 200 bootstrap resamples of runs")
    print("   (stratified by model) and, for the model share, 200 resamples of the 7 models (with replacement).\n")
    for out in OUTCOMES:
        y = df[out].to_numpy(float)
        point_l, point_g = decompose(df, y), decompose(df, y, logistic=True)
        boots = []
        for _ in range(200):
            idx = np.concatenate([RNG.choice(g.index.to_numpy(), len(g)) for _, g in df.groupby("model")])
            d = df.loc[idx].reset_index(drop=True)
            boots.append(decompose(d, d[out].to_numpy(float)))
        mboots = []
        models = sorted(df.model.unique())
        for _ in range(200):
            pick = RNG.choice(models, len(models))
            d = pd.concat([df[df.model == m].assign(model=f"{m}#{i}") for i, m in enumerate(pick)], ignore_index=True)
            mboots.append(decompose(d, d[out].to_numpy(float)))
        print(f"-- outcome: {out} (mean {y.mean():.3f}, n={len(y)})")
        print(f"   {'component':26s} {'LPM R2 [run bootstrap]':>34s} {'LPM [model bootstrap]':>26s} {'logistic dev. R2':>18s}")
        for k in point_l:
            b = [x[k] for x in boots]; mb = [x[k] for x in mboots]
            lo, hi = np.nanpercentile(b, [2.5, 97.5]) if np.isfinite(point_l[k]) else (np.nan, np.nan)
            mlo, mhi = np.nanpercentile(mb, [2.5, 97.5]) if np.isfinite(point_l[k]) else (np.nan, np.nan)
            print(f"   {k:26s} {point_l[k]:8.3f} [{lo:.3f}, {hi:.3f}]          [{mlo:.3f}, {mhi:.3f}]       {point_g[k]:8.3f}")
        print()


# ------------------------------------------------------------------ 2 few-shot calibration
def offset_fit(eta, y, prior_mu=None, prior_sd=None):
    """Estimate one intercept a so that y ~ Bernoulli(sig(a + eta)); Firth (Jeffreys) penalty for one parameter."""
    a = 0.0 if prior_mu is None else prior_mu
    for _ in range(100):
        p = sig(a + eta); w = p * (1 - p); I = w.sum() + 1e-9
        h = w / I
        u = np.sum(y - p) + np.sum(h * (0.5 - p))
        step = u / I
        step = max(-3, min(3, step))
        a += step
        if abs(step) < 1e-8:
            break
    return a


def part2(df):
    print("=" * 100)
    print("2. FEW-SHOT CALIBRATION (leave one model out; 200 random probe draws per k)")
    print("   P_cfg+offset: configuration effects fitted on the other 6 models (with their own intercepts), plus the")
    print("                 held-out model's intercept estimated from its k probe runs (Firth, offset only)")
    print("   P_own:        the model's own probe mean, Jeffreys-smoothed (s+0.5)/(k+1)  [no configuration information]")
    print("   P_pool:       the other 6 models' pooled rate                                [no information about the model]")
    print("   P_cap:        configuration + capability score fitted on the other 6 (Amendment 4 §4; no probes)")
    print("   Probes: k distinct configurations at random, one run each (k=10, 20); one run per configuration (48); two per")
    print("   configuration (96). Evaluation = that model's remaining runs. Numbers: median [2.5%, 97.5%] over the draws.")
    print("   dBrier = Brier(P_own) - Brier(P_cfg+offset): > 0 means configuration effects help beyond the model's own rate.\n")
    models = sorted(df.model.unique())
    C_all, cn = config_cols(df)
    summary = []
    for out in OUTCOMES:
        print(f"-- outcome: {out}")
        for m in models:
            tr, te_all = df[df.model != m], df[df.model == m]
            trm = sorted(tr.model.unique())
            Ctr, _ = config_cols(tr)
            X = np.column_stack([np.ones(len(tr)), dummies(tr.model, trm), Ctr])
            b, _, how = fit(X, tr[out].to_numpy(float))
            beta = b[len(trm):]                       # config effects
            ints = np.r_[b[0], b[0] + b[1:len(trm)]]  # training-model intercepts
            Cte, _ = config_cols(te_all)
            eta_all = Cte @ beta
            # capability model
            mu, sd = np.mean([CAP[x] for x in trm]), np.std([CAP[x] for x in trm])
            Xc = np.column_stack([np.ones(len(tr)), Ctr, (tr.cap - mu) / sd])
            bc, _, _ = fit(Xc, tr[out].to_numpy(float))
            p_cap_all = sig(np.column_stack([np.ones(len(te_all)), Cte, (te_all.cap - mu) / sd]) @ bc)
            pool = tr[out].mean()
            y_all = te_all[out].to_numpy(float)
            cfg = te_all.cfg_id.to_numpy()
            by_cfg = {c: np.flatnonzero(cfg == c) for c in np.unique(cfg)}
            print(f"   {m} (observed rate {y_all.mean():.3f}; config fit on others: {how})")
            for k in [10, 20, 48, 96]:
                res = {key: [] for key in ["cfg", "own", "pool", "cap", "d", "cal_cfg", "slope_cfg", "err_cfg", "err_own", "cal_own"]}
                for _ in range(200):
                    if k <= 48:
                        cs = RNG.choice(list(by_cfg), k, replace=False)
                        probe = np.array([RNG.choice(by_cfg[c]) for c in cs])
                    else:
                        probe = np.concatenate([RNG.choice(by_cfg[c], 2, replace=False) for c in by_cfg])
                    ev = np.setdiff1d(np.arange(len(y_all)), probe)
                    a = offset_fit(eta_all[probe], y_all[probe])
                    p1 = sig(a + eta_all[ev]); y = y_all[ev]
                    p0 = np.full(len(ev), (y_all[probe].sum() + 0.5) / (k + 1))
                    b1, b0 = brier(p1, y), brier(p0, y)
                    res["cfg"].append(b1); res["own"].append(b0)
                    res["pool"].append(brier(np.full(len(ev), pool), y)); res["cap"].append(brier(p_cap_all[ev], y))
                    res["d"].append(b0 - b1)
                    res["cal_cfg"].append(p1.mean() - y.mean()); res["cal_own"].append(p0.mean() - y.mean())
                    res["slope_cfg"].append(cal_slope(p1, y)[1] if 0 < y.sum() < len(y) else np.nan)
                    res["err_cfg"].append(abs(p1.mean() - y.mean())); res["err_own"].append(abs(p0.mean() - y.mean()))
                summary.append(dict(outcome=out, model=m, k=k, **{f"med_{x}": np.nanmedian(v) for x, v in res.items()},
                                    d_lo=np.percentile(res["d"], 2.5), d_hi=np.percentile(res["d"], 97.5),
                                    frac_d_pos=np.mean(np.array(res["d"]) > 0)))
                print(f"     k={k:3d}  Brier cfg+offset {fmtp(res['cfg'])}  own {fmtp(res['own'])}  pool {np.median(res['pool']):.4f}"
                      f"  cap {np.median(res['cap']):.4f}")
                print(f"            dBrier {fmt(res['d'])} (>0 in {np.mean(np.array(res['d']) > 0):.0%} of draws);"
                      f"  calib-in-large cfg {fmt(res['cal_cfg'])} own {fmt(res['cal_own'])};  slope cfg {fmtp(res['slope_cfg'])}")
        print()
    s = pd.DataFrame(summary)
    print("   SUMMARY: median dBrier (own - cfg+offset) per model and k; skill vs own = dBrier / Brier(own)")
    for out in OUTCOMES:
        t = s[s.outcome == out].pivot(index="model", columns="k", values="med_d")
        sk = s[s.outcome == out].assign(sk=lambda x: x.med_d / x.med_own).pivot(index="model", columns="k", values="sk")
        print(f"   {out}: dBrier\n" + t.round(4).to_string())
        print(f"   {out}: skill relative to own-mean baseline\n" + sk.round(3).to_string())
        print(f"   {out}: mean over models of median dBrier: " +
              ", ".join(f"k={k}: {t[k].mean():+.4f}" for k in t.columns) + "\n")
    return s


# ------------------------------------------------------------------ 3 within-model validation
def part3(df):
    print("=" * 100)
    print("3. WITHIN-MODEL PREDICTION: configuration-only model (7 factors, Firth) fitted on one model's own runs.")
    print("   Held-out family: 10 folds (train on 9 families, predict the 10th). Held-out configuration: 48 folds.")
    print("   Baseline: the training folds' mean rate. Skill = 1 - Brier/Brier(baseline); 200 bootstrap resamples of the")
    print("   pooled out-of-fold predictions give the interval. Also out-of-fold AUC.\n")
    rows = []
    for out in OUTCOMES:
        print(f"-- outcome: {out}")
        for m in sorted(df.model.unique()):
            g = df[df.model == m].reset_index(drop=True)
            y = g[out].to_numpy(float)
            C, _ = config_cols(g)
            X = np.column_stack([np.ones(len(g)), C])
            line = f"   {m:24s} rate {y.mean():.3f}"
            for name, key in [("family", "family"), ("config", "cfg_id")]:
                p = np.zeros(len(g)); p0 = np.zeros(len(g))
                for v in g[key].unique():
                    te = (g[key] == v).to_numpy(); trn = ~te
                    if y[trn].sum() == 0:
                        p[te] = p0[te] = 0.5 / (trn.sum() + 1)
                        continue
                    b, _, _ = fit(X[trn], y[trn], firth=True)
                    p[te] = sig(X[te] @ b); p0[te] = y[trn].mean()
                B, B0 = brier(p, y), brier(p0, y)
                sk = []
                for _ in range(200):
                    i = RNG.integers(0, len(y), len(y))
                    b0 = brier(p0[i], y[i]); sk.append(1 - brier(p[i], y[i]) / b0 if b0 > 0 else np.nan)
                lo, hi = np.nanpercentile(sk, [2.5, 97.5])
                auc = _auc(p, y)
                rows.append(dict(outcome=out, model=m, holdout=name, brier=B, brier_base=B0, skill=1 - B / B0 if B0 else np.nan,
                                 skill_lo=lo, skill_hi=hi, auc=auc))
                line += f" | held-out {name}: Brier {B:.4f} vs {B0:.4f}, skill {1 - B / B0 if B0 else float('nan'):+.3f} [{lo:+.3f}, {hi:+.3f}], AUC {auc:.3f}"
            print(line)
        print()
    return pd.DataFrame(rows)


def _auc(p, y):
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.r_[pos, neg]); ranks = np.empty(len(order)); ranks[order] = np.arange(1, len(order) + 1)
    # average ties
    allp = np.r_[pos, neg]
    for v in np.unique(allp):
        idx = allp == v
        if idx.sum() > 1:
            ranks[idx] = ranks[idx].mean()
    return (ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


# ------------------------------------------------------------------ 4 rule-following baseline
def part4(df):
    print("=" * 100)
    print("4. RULE-FOLLOWING BASELINE: honest path open, conflict none (nothing to gain, input present). Wilson 95%.\n")
    base = []
    for m in sorted(df.model.unique()):
        g = df[(df.model == m) & (df.honest_path == "open") & (df.conflict == "none")]
        a, r = int(g.attempt.sum()), int(g.read.sum())
        allg = df[df.model == m]
        base.append(dict(model=m, n=len(g), attempt=a / len(g), read=r / len(g), overall_attempt=allg.attempt.mean(), cap=CAP[m]))
        print(f"   {m:24s} attempt {rate(a, len(g))}   read {rate(r, len(g))}   (overall attempt {allg.attempt.mean():.3f}, capability {CAP[m]})")
    print("\n   Nemotron by input present (honest_path=open) / absent (blocked) x conflict:")
    n = df[df.model == "nemotron-3.5-lightning"]
    for hp, lab in [("open", "input present"), ("blocked", "input absent ")]:
        for c in ["none", "soft", "hard"]:
            g = n[(n.honest_path == hp) & (n.conflict == c)]
            print(f"     {lab} conflict={c:4s} attempt {rate(int(g.attempt.sum()), len(g))}  read {rate(int(g.read.sum()), len(g))}")
    print("\n   Same breakdown, all models (attempt rate, input present | absent):")
    t = df.pivot_table(index="model", columns=["honest_path", "conflict"], values="attempt", aggfunc="mean").round(3)
    print(t.to_string())
    b = pd.DataFrame(base)
    print("\n   Does the baseline order the models' overall attempt rates? Spearman rho(baseline attempt, overall attempt) ="
          f" {b.attempt.rank().corr(b.overall_attempt.rank()):.2f};  rho(capability, overall) = {b.cap.rank().corr(b.overall_attempt.rank()):.2f}"
          "  (7 models; descriptive)")
    # baseline as covariate in the leave-one-model-out prediction (replacing capability)
    print("\n   Baseline as a model-level covariate in the leave-one-model-out prediction (config + covariate, no probes),")
    print("   compared with capability. The baseline is measured on the held-out model's own open/none runs (those runs")
    print("   are then excluded from its evaluation).")
    for out in OUTCOMES:
        res = []
        for m in sorted(df.model.unique()):
            tr, te = df[df.model != m], df[df.model == m]
            te = te[~((te.honest_path == "open") & (te.conflict == "none"))]
            bl = {x: logit_rate(df[(df.model == x) & (df.honest_path == "open") & (df.conflict == "none")][out]) for x in df.model.unique()}
            out_row = {"model": m}
            for name, cov in [("capability", lambda d: d.cap.astype(float)), ("baseline", lambda d: d.model.map(bl))]:
                v = cov(tr); mu, sd = v.drop_duplicates().mean(), v.drop_duplicates().std(ddof=0)
                Ctr, _ = config_cols(tr); Cte, _ = config_cols(te)
                bb, _, _ = fit(np.column_stack([np.ones(len(tr)), Ctr, (v - mu) / sd]), tr[out].to_numpy(float))
                p = sig(np.column_stack([np.ones(len(te)), Cte, (cov(te) - mu) / sd]) @ bb)
                out_row[name] = (brier(p, te[out].to_numpy(float)), p.mean() - te[out].mean())
            out_row["pool"] = (brier(np.full(len(te), tr[out].mean()), te[out].to_numpy(float)), tr[out].mean() - te[out].mean())
            res.append(out_row)
        print(f"   -- {out}: Brier (rate error)")
        for r in res:
            print(f"      {r['model']:24s} capability {r['capability'][0]:.4f} ({r['capability'][1]:+.3f})   baseline {r['baseline'][0]:.4f}"
                  f" ({r['baseline'][1]:+.3f})   pooled {r['pool'][0]:.4f} ({r['pool'][1]:+.3f})")
        for name in ["capability", "baseline", "pool"]:
            print(f"      mean Brier {name}: {np.mean([r[name][0] for r in res]):.4f}; MAE of rate {np.mean([abs(r[name][1]) for r in res]):.4f}")
    print()


def logit_rate(s):
    p = (s.sum() + 0.5) / (len(s) + 1)
    return math.log(p / (1 - p))


# ------------------------------------------------------------------ 5 heterogeneity
def part5(df):
    print("=" * 100)
    print("5. HETEROGENEITY: per-model logistic regression (Firth) on all its runs, 7 factors; log-odds with 95% CI.")
    print("   Reference levels: escalation=credible, conflict=none, honest_path=open, privilege=low, monitoring=none,")
    print("   stakes=none, framing=neutral. Also raw rate differences for escalation (conflict != none).\n")
    show = ["escalation=none", "escalation=nominal", "honest_path=blocked", "conflict=soft", "conflict=hard",
            "monitoring=stated", "monitoring=visible", "stakes=task_failure", "stakes=shutdown", "framing=persona", "privilege=high"]
    allrows = []
    for out in OUTCOMES:
        print(f"-- outcome: {out}")
        tab = {}
        for m in sorted(df.model.unique()):
            g = df[df.model == m]
            C, cn = config_cols(g)
            b, se, _ = fit(np.column_stack([np.ones(len(g)), C]), g[out].to_numpy(float), firth=True)
            for nm in show:
                j = cn.index(nm) + 1
                tab.setdefault(nm, {})[m] = (b[j], b[j] - 1.96 * se[j], b[j] + 1.96 * se[j])
                allrows.append(dict(outcome=out, model=m, term=nm, b=b[j], lo=b[j] - 1.96 * se[j], hi=b[j] + 1.96 * se[j]))
        models = sorted(df.model.unique())
        short = {m: m.split("-")[0][:8] for m in models}
        print("   " + f"{'term':22s}" + "".join(f"{short[m]:>22s}" for m in models) + "   +sig/-sig/ns")
        for nm in show:
            cells, pos, neg = [], 0, 0
            for m in models:
                bb, lo, hi = tab[nm][m]
                mark = "+" if lo > 0 else ("-" if hi < 0 else " ")
                pos += lo > 0; neg += hi < 0
                cells.append(f"{bb:+6.2f} [{lo:+.1f},{hi:+.1f}]{mark}")
            print("   " + f"{nm:22s}" + "".join(f"{c:>22s}" for c in cells) + f"   {pos}/{neg}/{len(models) - pos - neg}")
        print("\n   escalation none - credible, raw rate difference (conflict != none), Newcombe 95%:")
        for m in models:
            g = df[(df.model == m) & (df.conflict != "none")]
            a, b_ = g[g.escalation == "none"][out], g[g.escalation == "credible"][out]
            d, lo, hi = newcombe(int(a.sum()), len(a), int(b_.sum()), len(b_))
            print(f"     {m:24s} {a.mean():.3f} - {b_.mean():.3f} = {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
        print()
    return pd.DataFrame(allrows)


def newcombe(k1, n1, k2, n2):
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1); l2, u2 = wilson(k2, n2)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def main():
    d6, d7 = Path(sys.argv[1]), Path(sys.argv[2])
    out = Path(__file__).parent / "data" / "dev"
    out.mkdir(exist_ok=True)
    df = load(d6, d7)
    print(f"development set: {len(df)} runs, models {df.groupby('model').size().to_dict()}")
    print(f"attempt (a4) rate {df.attempt.mean():.3f}; read rate {df.read.mean():.3f}\n")
    part4(df)
    part5(df).to_csv(out / "heterogeneity.csv", index=False)
    part3(df).to_csv(out / "within_model.csv", index=False)
    part2(df).to_csv(out / "fewshot_summary.csv", index=False)
    part1(df)


if __name__ == "__main__":
    main()
