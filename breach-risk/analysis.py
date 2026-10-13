"""Fit the breach-risk predictor and validate it out-of-sample.

  python analysis.py data/dryrun_synthetic/runs.csv

Predictors use only pre-deployment information: the 7 configuration factors plus model-level
covariates (training regime, capability score). Held-out splits: leave-one-model-out and
leave-one-scenario-family-out. Coefficient recovery vs known truth only runs on synthetic data.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from config import FACTORS, design_row, feature_names

warnings.filterwarnings("ignore")


def matrix(df: pd.DataFrame, with_model: bool = True) -> np.ndarray:
    X = np.array([design_row({f: r[f] for f in FACTORS}) for r in df.to_dict("records")])
    if with_model:
        X = np.column_stack([X, df.rl_heavy.values, df.capability.values])
    return X


def ece(y, p, bins=10):
    order = np.argsort(p)
    return float(sum(len(c) / len(y) * abs(p[c].mean() - y[c].mean()) for c in np.array_split(order, bins)))


def metrics(y, p):
    return {"brier": round(brier_score_loss(y, p), 4), "ece": round(ece(y, p), 4),
            "auroc": round(roc_auc_score(y, p), 3), "auprc": round(average_precision_score(y, p), 3)}


def fit_lr(X, y):
    return LogisticRegression(C=10.0, max_iter=3000, fit_intercept=False).fit(X, y)


def cross_validate(df, X, y, group_col):
    preds = {k: np.zeros(len(y)) for k in ["base_rate", "model_only", "full_logistic", "boosted_trees"]}
    z = X[:, -2:]
    Xraw = X[:, 1:]  # drop intercept column for trees
    for g in sorted(df[group_col].unique()):
        te = (df[group_col] == g).values
        tr = ~te
        preds["base_rate"][te] = y[tr].mean()
        zc = np.column_stack([np.ones(len(y)), z])
        preds["model_only"][te] = fit_lr(zc[tr], y[tr]).predict_proba(zc[te])[:, 1]
        preds["full_logistic"][te] = fit_lr(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, random_state=0).fit(Xraw[tr], y[tr])
        preds["boosted_trees"][te] = gb.predict_proba(Xraw[te])[:, 1]
    return {k: metrics(y, np.clip(v, 1e-6, 1 - 1e-6)) for k, v in preds.items()}, preds


def main(path):
    df = pd.read_csv(path)
    y = df.breach.values.astype(int)
    X = matrix(df)
    names = feature_names() + ["rl_heavy", "capability"]
    print(f"{len(df)} runs, {y.sum()} breaches ({y.mean():.2%}), {df.model.nunique()} models, {df.family.nunique()} task families\n")

    results = {}
    for label, col in [("Leave-one-model-out", "model"), ("Leave-one-task-family-out", "family")]:
        m, preds = cross_validate(df, X, y, col)
        results[label] = m
        print(f"## {label}  (every prediction made for a {col} the predictor never saw)")
        print(pd.DataFrame(m).T.to_string(), "\n")
        if col == "model":
            results["_lomo_preds"] = preds["full_logistic"]

    # Calibration of the held-out predictions
    p = results.pop("_lomo_preds")
    q = pd.qcut(p, 5, duplicates="drop")
    cal = pd.DataFrame({"pred": p, "obs": y, "bin": q}).groupby("bin", observed=True).agg(
        n=("obs", "size"), predicted=("pred", "mean"), observed=("obs", "mean")).round(4)
    print("## Calibration, leave-one-model-out full model (5 equal-count risk bins)")
    print(cal.to_string(index=False), "\n")
    results["calibration_lomo"] = cal.to_dict("records")

    # Effect estimates with uncertainty
    fit = sm.GLM(y, X, family=sm.families.Binomial()).fit()
    ci = fit.conf_int()
    synthetic = "source" in df and (df.source == "synthetic").all()
    if synthetic:
        from simulation import TRUE_COEF
    rows = []
    for i, n in enumerate(names):
        if n == "intercept":
            continue
        row = {"factor": n, "est": round(fit.params[i], 2), "ci95": f"[{ci[i][0]:.2f}, {ci[i][1]:.2f}]"}
        if synthetic and n not in ("rl_heavy", "capability"):
            t = TRUE_COEF.get(n, 0.0)
            row = {"factor": n, "true": t, **{k: row[k] for k in ("est", "ci95")}, "covered": bool(ci[i][0] <= t <= ci[i][1])}
        rows.append(row)
    rec = pd.DataFrame(rows)
    if synthetic:
        print("## Coefficient recovery (synthetic data only: truth is known)")
        print(rec.to_string(index=False))
        checked = rec["covered"].dropna()
        print(f"\n95% intervals containing the truth: {int(checked.sum())} of {len(checked)}")
    else:
        print("## Effect estimates (log-odds, 95% interval)")
        print(rec.to_string(index=False))
    results["effects"] = rows
    Path(path).with_name("analysis_results.json").write_text(json.dumps(results, indent=1, default=float))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/dryrun_synthetic/runs.csv")
