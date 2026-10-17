"""Amendment 13: EXPLORATORY yes/no prediction of high-risk configurations (no model calls). One pass.

  python analyze_yesno.py > data/yesno_exploratory/analysis.txt
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_attempters import probe_mask
from analyze_pilot6 import logit_fit
from evaluate_confirmation import X, firth_offset, load, sig

HERE = Path(__file__).parent
OUT = HERE / "data/yesno_exploratory"
B, SEED, MIN_RUNS = 2000, 2026, 10


def auc(score, y):
    pos, neg = score[y == 1], score[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def spearman(a, b):
    if np.std(a) == 0 or np.std(b) == 0:
        return np.nan
    ra, rb = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def metrics(pred_rate, obs_rate, thr):
    y = (obs_rate >= thr).astype(int)
    yh = (pred_rate >= thr).astype(int)
    tp, tn = int(((yh == 1) & (y == 1)).sum()), int(((yh == 0) & (y == 0)).sum())
    P, N = int(y.sum()), int((1 - y).sum())
    rec = tp / P if P else np.nan
    spec = tn / N if N else np.nan
    return dict(acc=(tp + tn) / len(y), bal_acc=np.nanmean([rec, spec]),
                precision=tp / yh.sum() if yh.sum() else np.nan, recall=rec,
                auc=auc(pred_rate, y), spearman=spearman(pred_rate, obs_rate))


def per_model(df, models, m, probes8, thr):
    tr = df[df.model.isin(models) & (df.model != m)]
    b, _, _ = logit_fit(X(tr), tr.attempt.to_numpy(float))
    g = df[df.model == m].reset_index(drop=True)
    pm = probe_mask(g, probes8)
    eta = X(g) @ b
    a = firth_offset(eta[pm], g.attempt.to_numpy(float)[pm])
    p0 = (g.attempt.to_numpy(float)[pm].sum() + 0.5) / (pm.sum() + 1)
    ev = g[~pm].assign(p_method=sig(a + eta[~pm]), p_nooff=sig(eta[~pm]))
    c = ev.groupby("cfg_id").agg(n=("attempt", "size"), obs=("attempt", "mean"), method=("p_method", "first"),
                                 nooff=("p_nooff", "first")).reset_index()
    c = c[c.n >= MIN_RUNS].reset_index(drop=True)
    c["own"] = p0
    return c


def run(df, models, probes8, thr, label, rows):
    print(f"======== {label} | threshold {thr:.0%} | {len(models)} models")
    rng = np.random.default_rng(SEED)
    for m in models:
        c = per_model(df, models, m, probes8, thr)
        y = (c.obs >= thr).astype(int).to_numpy()
        P, N = int(y.sum()), int(len(y) - y.sum())
        head = f"  {m:24s} configs {len(c)} (high-risk {P}, other {N})"
        if min(P, N) < 3:
            print(head + " -> too few to score")
            rows.append(dict(set=label, thr=thr, model=m, n_cfg=len(c), n_high=P, n_low=N, scored=False))
            continue
        res = {k: metrics(c[k].to_numpy(), c.obs.to_numpy(), thr) for k in ("method", "own", "nooff")}
        maj = int(P > N)
        res["majority"] = dict(acc=max(P, N) / len(y), bal_acc=0.5, precision=(P / len(y)) if maj else np.nan,
                               recall=float(maj), auc=0.5, spearman=np.nan)
        diffs, boot = [], {k: [] for k in ("bal_acc", "auc", "spearman")}
        for _ in range(B):
            ix = rng.integers(0, len(c), len(c))
            s = c.iloc[ix]
            mm = metrics(s.method.to_numpy(), s.obs.to_numpy(), thr)
            mo = metrics(s.own.to_numpy(), s.obs.to_numpy(), thr)
            diffs.append(mm["bal_acc"] - mo["bal_acc"])
            for k in boot:
                boot[k].append(mm[k])
        lo, hi = np.nanpercentile(diffs, [2.5, 97.5])
        verdict = "BEATS" if lo > 0 else "LOSES" if hi < 0 else "ties"
        r = res["method"]
        fmt = lambda v: "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.2f}"
        print(head + f" | method: acc {fmt(r['acc'])} bal {fmt(r['bal_acc'])} prec {fmt(r['precision'])} rec {fmt(r['recall'])} "
              f"AUC {fmt(r['auc'])} rho {fmt(r['spearman'])} | (a) own-avg bal {fmt(res['own']['bal_acc'])} "
              f"(b) majority acc {fmt(res['majority']['acc'])} (c) no-offset bal {fmt(res['nooff']['bal_acc'])} AUC {fmt(res['nooff']['auc'])} "
              f"| bal diff vs (a) {np.mean(diffs):+.2f} [{lo:+.2f}, {hi:+.2f}] -> {verdict}")
        rows.append(dict(set=label, thr=thr, model=m, n_cfg=len(c), n_high=P, n_low=N, scored=True, verdict=verdict,
                         bal_diff_lo=lo, bal_diff_hi=hi,
                         **{f"{k}_{s}": v for k, d in res.items() for s, v in d.items()},
                         **{f"boot_{k}": np.array(v) for k, v in boot.items()}))
    sc = [r for r in rows if r["set"] == label and r["thr"] == thr and r.get("scored")]
    if sc:
        print(f"  POOLED ({len(sc)} scored): beats (a) {sum(r['verdict'] == 'BEATS' for r in sc)}, "
              f"ties {sum(r['verdict'] == 'ties' for r in sc)}, loses {sum(r['verdict'] == 'LOSES' for r in sc)}")
        for k in ("acc", "bal_acc", "precision", "recall", "auc", "spearman"):
            v = np.array([r[f"method_{k}"] for r in sc], float)
            line = f"    {k:9s} median {np.nanmedian(v):.2f} range [{np.nanmin(v):.2f}, {np.nanmax(v):.2f}]"
            if k in ("bal_acc", "auc", "spearman"):
                meds = np.nanmedian(np.vstack([r[f"boot_{k}"] for r in sc]), axis=0)
                line += f"  median 95% CI [{np.nanpercentile(meds, 2.5):.2f}, {np.nanpercentile(meds, 97.5):.2f}]"
            print(line)
    print()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.concat([load(HERE / f"data/pilot{p}") for p in (6, 7, 8)], ignore_index=True)
    probes8 = {k for v in json.load(open(HERE / "data/pilot8/probe_sets.json")).values() for k in v}
    rates = df.groupby("model").attempt.mean()
    att = rates[rates >= 0.05].sort_values(ascending=False).index.tolist()
    allm = rates.sort_values(ascending=False).index.tolist()
    rows = []
    for thr in (0.20, 0.10, 0.30):
        tag = "PRIMARY" if thr == 0.20 else "sensitivity"
        run(df, att, probes8, thr, f"attempters ({tag})", rows)
        run(df, allm, probes8, thr, f"all 12 ({tag})", rows)
    pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("boot_")} for r in rows]).to_csv(OUT / "results.csv", index=False)


if __name__ == "__main__":
    main()
