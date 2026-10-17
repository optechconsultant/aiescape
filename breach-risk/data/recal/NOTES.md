# Recalibration with a scale parameter: EXPLORATORY (pilots 6–8, 12 models)

`python analyze_recal.py > data/recal/analysis_recal.txt` (table also in `recal.csv`). No model calls; no claim is
confirmatory. Pilot 8 was scored under Amendment 7 with the offset-only method; nothing here changes that result.

Method: hold out each model; fit pooled configuration effects (7 factors, no model terms) on the other 11 models.
From the held-out model's 48 probe runs fit either an offset only (**current**) or an offset plus a scale on the pooled
effects (**scaled**; Firth). Score on its remaining runs. Probe sets: pilot 8's preregistered sets; pilots 6–7 one
run per configuration (seeded). Robustness: 200 random probe draws per model.

## Attempts (primary outcome)
- **Brier:** scaled is better for 5 of 12 models on the fixed probe set and for 7 of 12 in most random draws, but
  the gains are small except for ling (0.137 → 0.124, better in 100% of draws) and qwen (0.113 → 0.107, 80%).
  It is worse for glm (0.101 → 0.109), and slightly worse for deepseek, scout, granite (fixed set), gpt-oss, mistral.
- **Calibration slope:** the current method's slope interval contains 1 for only 4 models (glm, gpt-oss, scout,
  mistral); most slopes are above 1 (pooled effects too weak for that model). The scale moves the slope towards 1
  for granite (2.43 → 0.94), ling (1.98 → 1.24), minimax (1.54 → 0.89), mimo (0.74 → 1.01), nemotron (1.34 → 1.06),
  qwen (1.74 → 0.81), gemma (2.31 → 2.01); the interval then contains 1 for granite, mimo, nemotron and (borderline)
  minimax. It overshoots for glm (s = 5.4, slope 0.22) and scout (s = 0.35, slope 2.27).
- **Rare-outcome models break it:** with very few events in 48 probes (gpt-oss, mistral) the scale is estimated near
  0 or negative, and the slope becomes meaningless (about −20).
- **Calibration in the large** barely changes (both methods within about ±6 points everywhere).

## Reads (descriptive)
Scaled helps only for ling (+0.008) and qwen (+0.009); for most models reads are rare and the scale is unstable
(negative for deepseek, gemma, gpt-oss, mistral), making Brier slightly worse.

## Plain conclusion
A scale estimated from 48 probes fixes the systematic "pooled effects too weak" miscalibration for models with
plenty of events (ling, qwen, granite, minimax, nemotron), but it is noisy and sometimes harmful when a model has
few events or a different pattern (glm, scout, gpt-oss, mistral). Unrestricted, it is not a safe default. A shrunken
scale (pulled towards 1, or only used above a minimum number of probe events) is the obvious next thing to test;
it was not tested here.
