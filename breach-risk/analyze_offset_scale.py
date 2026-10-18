"""Amendment 16 Part 1 (EXPLORATORY): offset + scale prediction vs offset only vs own average, 12 models.

  python analyze_offset_scale.py   # -> paper_data_pack/P1_offset_scale.csv, P1_practice_size.csv
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from analyze_pilot6 import logit_fit
from evaluate_confirmation import X, cal, firth_offset, load, sig

HERE = Path(__file__).parent
OUT = HERE.parent / "paper_data_pack"
SEED, B = 2026, 2000


def practice_masks(g: pd.DataFrame, probes8: set) -> dict[int, np.ndarray]:
    """48-run set as before; 96 and 192 add 1 and 3 more runs per configuration in a seeded shuffle order."""
    order = np.random.default_rng(SEED).permutation(len(g))
    cfg = g.cfg_id.to_numpy()
    base = g.key.isin(probes8).to_numpy() if g.key.isin(probes8).any() else None
    if base is None:
        base, seen = np.zeros(len(g), bool), set()
        for i in order:
            if cfg[i] not in seen:
                seen.add(cfg[i]); base[i] = True
    out = {48: base}
    for k, per in ((96, 2), (192, 4)):
        m = base.copy()
        count = pd.Series(m.astype(int)).groupby(cfg).sum().to_dict()
        for i in order:
            if not m[i] and count[cfg[i]] < per:
                m[i] = True; count[cfg[i]] += 1
        out[k] = m
    return out


def fit_predict(lp, y, prac, ev):
    a = firth_offset(lp[prac], y[prac])
    b, _, _ = logit_fit(np.column_stack([np.ones(prac.sum()), lp[prac]]), y[prac], firth=True)
    own = (y[prac].sum() + 0.5) / (prac.sum() + 1)
    return sig(b[0] + b[1] * lp[ev]), sig(a + lp[ev]), np.full(ev.sum(), own), b


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def boot(y, ps, cfg, rng):
    idx_by = [np.flatnonzero(cfg == c) for c in np.unique(cfg)]
    out = []
    for _ in range(B):
        i = np.concatenate([rng.choice(ix, len(ix)) for ix in idx_by])
        out.append([brier(p[i], y[i]) for p in ps])
    return np.array(out)


def main():
    df = pd.concat([load(HERE / f"data/pilot{p}") for p in (6, 7, 8)], ignore_index=True)
    probes8 = {k for v in json.load(open(HERE / "data/pilot8/probe_sets.json")).values() for k in v}
    rng = np.random.default_rng(SEED)
    rows, sizes, boots = [], [], []
    for m in sorted(df.model.unique()):
        tr = df[df.model != m]
        bpool, _, _ = logit_fit(X(tr), tr.attempt.to_numpy(float))
        g = df[df.model == m].reset_index(drop=True)
        y, lp, cfg = g.attempt.to_numpy(float), X(g) @ bpool, g.cfg_id.to_numpy()
        masks = practice_masks(g, probes8)
        prac = masks[48]; ev = ~prac
        p2, p1, p0, b = fit_predict(lp, y, prac, ev)
        ye = y[ev]
        res = {}
        for name, p in (("scale", p2), ("offset", p1)):
            s, (lo, hi) = cal(p, ye)
            citl = p.mean() - ye.mean()
            res[name] = dict(slope=s, lo=lo, hi=hi, citl=citl, ok=bool(np.isfinite(lo) and lo <= 1 <= hi and abs(citl) <= 0.05))
        bo = boot(ye, (p0, p1, p2), cfg[ev], rng)
        boots.append(bo)
        g_own = bo[:, 0] - bo[:, 2]; g_off = bo[:, 1] - bo[:, 2]
        rows.append(dict(model=m, practice_events=int(y[prac].sum()), eval_runs=int(ev.sum()), eval_rate=ye.mean(),
                         a=b[0], b=b[1],
                         slope_scale=res["scale"]["slope"], slope_scale_lo=res["scale"]["lo"], slope_scale_hi=res["scale"]["hi"],
                         citl_scale=res["scale"]["citl"], calib_pass_scale=res["scale"]["ok"],
                         slope_offset=res["offset"]["slope"], slope_offset_lo=res["offset"]["lo"], slope_offset_hi=res["offset"]["hi"],
                         citl_offset=res["offset"]["citl"], calib_pass_offset=res["offset"]["ok"],
                         brier_own=brier(p0, ye), brier_offset=brier(p1, ye), brier_scale=brier(p2, ye),
                         gain_vs_own=brier(p0, ye) - brier(p2, ye), gain_vs_own_lo=np.percentile(g_own, 2.5), gain_vs_own_hi=np.percentile(g_own, 97.5),
                         gain_vs_offset=brier(p1, ye) - brier(p2, ye), gain_vs_offset_lo=np.percentile(g_off, 2.5),
                         gain_vs_offset_hi=np.percentile(g_off, 97.5)))
        common = ~masks[192]
        for k in (48, 96, 192):
            q2, q1, q0, bk = fit_predict(lp, y, masks[k], common)
            yc = y[common]
            s, (lo, hi) = cal(q2, yc)
            sizes.append(dict(model=m, practice_runs=int(masks[k].sum()), practice_events=int(y[masks[k]].sum()), eval_runs=int(common.sum()),
                              b=bk[1], slope=s, slope_lo=lo, slope_hi=hi, citl=q2.mean() - yc.mean(),
                              calib_pass=bool(np.isfinite(lo) and lo <= 1 <= hi and abs(q2.mean() - yc.mean()) <= 0.05),
                              brier_own=brier(q0, yc), brier_offset=brier(q1, yc), brier_scale=brier(q2, yc)))
    t = pd.DataFrame(rows)
    pooled = np.mean(np.stack(boots), axis=0)  # B x 3: mean over models of own, offset, scale Brier
    po, pf = pooled[:, 0] - pooled[:, 2], pooled[:, 1] - pooled[:, 2]
    t.loc[len(t)] = dict(model="POOLED (mean of 12)", gain_vs_own=t.gain_vs_own.mean(), gain_vs_own_lo=np.percentile(po, 2.5),
                         gain_vs_own_hi=np.percentile(po, 97.5), gain_vs_offset=t.gain_vs_offset.mean(),
                         gain_vs_offset_lo=np.percentile(pf, 2.5), gain_vs_offset_hi=np.percentile(pf, 97.5),
                         calib_pass_scale=int(t.calib_pass_scale.sum()), calib_pass_offset=int(t.calib_pass_offset.sum()))
    t.to_csv(OUT / "P1_offset_scale.csv", index=False)
    s = pd.DataFrame(sizes)
    s.to_csv(OUT / "P1_practice_size.csv", index=False)
    pd.set_option("display.width", 250)
    print(t.round(4).to_string(index=False))
    print(s.groupby("practice_runs").agg(models_passing=("calib_pass", "sum"), median_slope=("slope", "median"),
                                         mean_brier_scale=("brier_scale", "mean"), mean_brier_offset=("brier_offset", "mean"),
                                         mean_brier_own=("brier_own", "mean")).round(4).to_string())


if __name__ == "__main__":
    main()
