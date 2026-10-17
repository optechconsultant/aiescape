# Yes/no high-risk configuration prediction — EXPLORATORY (Amendment 13). Not confirmation.

`python analyze_yesno.py > analysis.txt`; per-model numbers in `results.csv`. One pass, no model calls, no spend.
Every model has all 48 configurations scored (19–29 evaluation runs each, probe runs excluded).

## Primary (attempters, high-risk = observed a4 rate ≥ 20%)
| model | high / other configs | bal. acc | AUC | Spearman | vs (a) own average: bal. acc diff [95%] | (c) no offset bal. acc |
| --- | --- | --- | --- | --- | --- | --- |
| nemotron | 40 / 8 | 0.68 | 0.93 | 0.85 | +0.18 [−0.01, +0.36] ties | 0.74 |
| ling | 33 / 15 | 0.73 | 0.98 | 0.89 | +0.23 [+0.11, +0.36] BEATS | 0.82 |
| minimax | 19 / 29 | 0.93 | 0.97 | 0.81 | +0.43 [+0.37, +0.48] BEATS | 0.93 |
| deepseek | 20 / 28 | 0.76 | 0.92 | 0.83 | +0.27 [+0.14, +0.38] BEATS | 0.90 |
| mimo | 24 / 24 | 0.77 | 0.88 | 0.69 | +0.27 [+0.15, +0.39] BEATS | 0.77 |
| qwen | 14 / 34 | 0.69 | 0.86 | 0.67 | +0.19 [+0.03, +0.33] BEATS | 0.78 |
| glm | 15 / 33 | 0.82 | 0.88 | 0.80 | +0.32 [+0.18, +0.44] BEATS | 0.68 |
| granite | 8 / 40 | 0.97 | 0.99 | 0.77 | +0.47 [+0.44, +0.50] BEATS | 0.81 |
| gemma | 7 / 41 | 0.50 | 0.99 | 0.73 | +0.00 ties (predicts no config high-risk) | 0.80 |
| scout | 4 / 44 | 0.72 | 0.78 | 0.52 | +0.21 [−0.06, +0.48] ties | 0.65 |
Pooled: beats (a) 7/10, ties 3, loses 0. Median balanced accuracy 0.75 (range 0.50–0.97, 95% CI of median
[0.69, 0.82]); median AUC 0.93 (0.78–0.99, [0.90, 0.98]); median Spearman 0.78 (0.52–0.89, [0.71, 0.82]).
All 12: same 10 scored (mistral and gpt-oss have no high-risk configuration: too few to score), same 7/10.
Sensitivity: 10% threshold 6/10 beat (nemotron and ling tie: nearly every config is above 10%); 30% threshold 7/9
(scout too few to score). Same picture at every threshold.

## Reading
- **Ranking works for every model**: which situations a model attempts in is well ordered by the pooled
  configuration effects (AUC 0.78–0.99). Not driven by ling/nemotron: nemotron is one of the ties.
- **The yes/no cut is where it fails**, and it fails because of the offset (the level), not the ranking:
  gemma ranks almost perfectly (AUC 0.99) but its offset from 1 probe attempt puts every prediction under 20%
  (recall 0); nemotron has only 8 non-high-risk configs, so balanced accuracy is noisy; scout has 4 high-risk configs.
- **The per-model offset does not help the yes/no call on average:** baseline (c) (no offset at all) matches or beats
  the method for 6 of 10 models (e.g. deepseek 0.90 vs 0.76, ling 0.82 vs 0.73, gemma 0.80 vs 0.50). The offset
  cannot change the ranking (AUC is identical), and from 48 probes it often moves the level the wrong way.
- Baseline (a) is weak by construction (it predicts one class for every config, balanced accuracy 0.5), so
  "beats (a)" only shows that configuration information helps at all.
- Config noise: ~19 evaluation runs per configuration, so an observed 20% has a standard error of ~9 points;
  configurations near the threshold are labelled with noise.
- Exploratory: these data were analysed before; the probe sets for pilots 6–7 were drawn for analysis.
