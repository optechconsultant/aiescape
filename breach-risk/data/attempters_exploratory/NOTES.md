# Attempters-only calibration re-analysis — EXPLORATORY, post-hoc (Amendment 12). Not confirmation.

`python analyze_attempters.py > analysis.txt`; per-model numbers in `results.csv`, attempt rates in
`attempt_rates.csv`, reliability tables (deciles of predicted probability) in `reliability.csv`. One pass, no
retuning, no model calls, no spend. 12 models in the 48-configuration design (pilots 6–8); Haiku and ladder data
excluded.

## Attempters (a4 rate ≥ 5%): 10 of 12
nemotron 67.0%, ling 48.8%, minimax 23.8%, deepseek 20.5%, mimo 19.8%, qwen 18.8%, glm 14.4%, granite 8.9%,
gemma 7.8% (borderline), scout 5.2% (borderline). Not attempters: mistral 0.8%, gpt-oss 0.4%. The 3% cutoff gives
the same 10 models; the 10% cutoff drops granite, gemma and scout (7 models).

## Calibration slope (C2 needs the 95% interval to contain 1 and |CITL| ≤ 0.05)
| model | all 12 | attempters ≥5% (=≥3%) | attempters ≥10% |
| --- | --- | --- | --- |
| nemotron | 1.34 [1.16, 1.51] | 1.25 [1.08, 1.42] | 1.21 [1.05, 1.38] |
| ling | 1.98 [1.74, 2.22] | 1.88 [1.65, 2.11] | 1.78 [1.57, 2.00] |
| minimax | 1.54 [1.31, 1.77] | 1.40 [1.19, 1.61] | 1.32 [1.12, 1.51] |
| deepseek | 1.32 [1.10, 1.53] | 1.21 [1.01, 1.40] | 1.14 [0.96, 1.33] (CITL −0.057 fails) |
| mimo | 0.74 [0.58, 0.90] | 0.68 [0.53, 0.82] | 0.62 [0.48, 0.75] |
| qwen | 1.74 [1.52, 1.97] | 1.59 [1.38, 1.79] | 1.43 [1.24, 1.62] |
| glm | 1.21 [0.97, 1.45] PASS | 1.13 [0.91, 1.35] PASS | 1.02 [0.81, 1.22] PASS |
| granite | 2.43 [1.92, 2.94] | 2.14 [1.69, 2.58] | — |
| gemma | 2.31 [1.80, 2.81] | 2.03 [1.60, 2.47] | — |
| scout | 0.79 [0.49, 1.09] PASS | 0.72 [0.45, 0.99] | — |
| mistral | 1.35 [0.60, 2.10] PASS | — | — |
| gpt-oss | 1.37 [0.05, 2.68] PASS | — | — |
| **C2 passes** | **4/12** | **1/10** | **1/7** |
| pooled C1 (mean D) | +0.032 [+0.031, +0.034], 9/12 PASS | +0.039 [+0.037, +0.041], 9/10 PASS | +0.051 [+0.048, +0.054], 6/7 PASS |

## Reading
- Restricting to attempters moves most slopes a little towards 1 (pooled effects fitted on attempters only are a
  bit stronger), but they stay clearly above 1 (ling, qwen, minimax, granite, gemma, nemotron) or below 1 (mimo).
  Only glm passes C2 in every set. **C2 does not improve; the pass count falls (4/12 -> 1/10 -> 1/7)** because the
  all-model "passes" were the rare models (mistral, gpt-oss, scout) whose intervals are wide enough to contain 1.
- C1 holds in every set; it is not what was in doubt.
- The cutoff (3%, 5%, 10%) does not change the answer.
- Fragile points: gemma has 1 attempt in its 48 probes and scout 3 (offsets rest on 1–3 events); the pilot 6–7 probe
  sets were drawn for this analysis (seeded), not preregistered; ling and nemotron drive the pooled C1 gain;
  the interval widths (±0.2 for frequent attempters) are narrow enough that the miscalibration is real, not noise.
- **Conclusion: this does not justify a fresh-model confirmation of calibration (C2) for attempters.** Within this
  data the miscalibration is model-specific (slope too steep or too shallow per model), not a rare-event artefact.
