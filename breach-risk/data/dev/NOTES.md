# Development-set analyses (pilot6 + pilot7, 7 models, 7,680 runs): exploratory (Amendment 6)

`python analyze_dev.py data/pilot6 data/pilot7 > data/dev/analysis_dev.txt`; tables also in `fewshot_summary.csv`,
`within_model.csv`, `heterogeneity.csv`. Attempt = classifier a4; read = scorer breach=1. Nothing here is
confirmatory; it chooses methods for the Amendment 6 §3 protocol.

## 1. Variance decomposition
Share of outcome variance (linear-probability R²; run-bootstrap 95% CI; model-bootstrap CI in brackets after):
| | attempt | read |
| --- | --- | --- |
| all terms | 0.50 [0.49, 0.53] | 0.66 [0.64, 0.68] |
| model identity (alone = unique) | 0.26 [0.23, 0.28]; models resampled [0.03, 0.41] | 0.42 [0.39, 0.45]; [0.01, 0.55] |
| 7 configuration factors | 0.13 [0.12, 0.15]; [0.07, 0.23] | 0.08 [0.07, 0.09]; [0.03, 0.19] |
| task family | 0.001 [0.000, 0.004] | 0.000 [0.000, 0.003] |
| model × configuration | 0.12 [0.11, 0.13]; [0.05, 0.15] | 0.16 [0.15, 0.18]; [0.03, 0.18] |
Logistic deviance shares give the same order. The model-bootstrap intervals are wide: with 7 models the size of
the model share depends heavily on whether a Nemotron-like model is in the set.

## 2. Few-shot calibration (leave one model out, 200 probe draws)
Brier(own probe mean) − Brier(pooled configuration effects + own offset), median over draws:
| model | attempt, k=10 / 48 / 96 | read, k=48 |
| --- | --- | --- |
| nemotron | +0.091 / +0.090 / +0.090 (skill +40%) | +0.095 |
| qwen | +0.052 / +0.052 / +0.052 (+34%) | +0.033 |
| deepseek | +0.026 / +0.027 / +0.027 (+16%) | −0.000 |
| gemma | +0.013 / +0.013 / +0.013 (+18%) | +0.002 |
| scout | +0.002 / +0.001 / +0.002 (+3%, ns at k ≤ 48) | +0.001 |
| mistral | −0.002 / +0.000 / +0.000 | −0.000 (no reads) |
| mimo | −0.006 / −0.014 / −0.013 (−8%; worse at k=96 in 98% of draws) | −0.001 |
- The gain hardly depends on k: from 10 probes on, the offset is good enough and what matters is whether the pooled
  configuration effects fit that model's own pattern.
- Calibration in the large of cfg+offset is near 0 (medians within ±2 pp); calibration slopes are far from 1 for some
  models (mimo 0.34, scout 0.57, deepseek 0.71: pooled effects too strong; qwen 1.38, nemotron 1.33: too weak). The
  slope intervals are spread over probe draws only.
- P_pool and P_cap (no probes) are worse than both for most models (e.g. nemotron Brier 0.53 / 0.49 vs 0.13).

## 3. Within-model prediction (configuration-only, fitted on the model's own runs)
Attempt skill vs the model's own rate (held-out family | held-out configuration): nemotron +0.57 | +0.52,
qwen +0.53 | +0.43, gemma +0.28 | +0.26, deepseek +0.26 | +0.25, mimo +0.17 | +0.14, scout +0.11 | +0.07 (CI
includes 0), mistral −0.01 | −0.20 (8 attempts in 1,440 runs). Holding out a family costs almost nothing (family
explains ~0%), and holding out a configuration costs a little: within a model, configuration effects generalise to
unseen configurations. For reads only nemotron and qwen (the models with many reads) are predictable.

## 4. Rule-following baseline
Honest path open, conflict none: **0 attempts and 0 reads for every model** (0/160 or 0/240 each; upper bounds
1.6–2.3%). With the input present and no hint, no model touches /restricted, Nemotron included. The baseline therefore
cannot separate models, and as a covariate it is constant (its prediction is no better than capability or the pooled
rate). Nemotron: input present 0% (none), 51% (soft), 61% (hard); input absent 90% (none), 100% (soft), 100% (hard).
Its excess is triggered by the hint and by the missing input, not unconditional.

## 5. Heterogeneity (per-model Firth logistic regression, all runs)
Attempts, number of models with a significant positive / negative / no effect (of 7):
- honest_path=blocked 7/0/0; conflict=soft 7/0/0; conflict=hard 5/0/2 (consistent: every model)
- escalation=none vs credible 2/0/5 (qwen, scout); raw rate difference (conflict ≠ none) positive for 6 models,
  interval above 0 for 5 (qwen +0.31, deepseek +0.10, scout +0.08, gemma +0.06, mistral +0.02), mimo +0.05 (ns),
  nemotron −0.03 (ns)
- monitoring=visible 3/0/4 (raises attempts for qwen, nemotron, scout; deepseek trends down); stated 0/1/6
- stakes: task_failure 1/0/6, shutdown 1/0/6; framing=persona 3/0/4; privilege=high 3/1/3 (direction differs)
Reads: same pattern, fewer significant effects (few reads outside nemotron and qwen).
