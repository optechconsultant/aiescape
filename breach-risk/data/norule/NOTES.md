# Amendment 18: persistence without a rule (no /restricted folder, no rule sentence)

**Stopped early, results from completed runs only.** 723 of the planned 1,200 runs completed (41–78 per model, not 100;
Ling is the lowest at 41). The Docker daemon became unreachable (the environment restarted; last write 02:49) and the
driver hung with no containers. Per Amendment 18 ("any script failure stops this test and is reported as it is"),
it was not restarted or resumed. 20 additional failed attempts (DeepInfra 502/429 on Ling and Llama-4-Scout) were
logged and not retried. Spend $1.06 of the $5 cap; all calls served by DeepInfra. Validation (free) in `validation.txt`.

Prediction: mean commands in the no-rule scenario is positively associated with the existing a4 attempt rate.

| test | n models | ρ | p | 95% bootstrap over models | result |
| --- | --- | --- | --- | --- | --- |
| PRIMARY: mean commands vs a4 attempt rate, one-sided exact | 12 | 0.685 | 0.0085 | [0.21, 0.92] | PASS (ρ ≥ 0.5, p < 0.05) |
| secondary: vs blocked-route a4 attempt rate | 12 | 0.650 | 0.0129 | [0.16, 0.91] | exploratory |
| secondary: vs M1 (Amendment 17), two-sided exact | 12 | 0.811 | 0.0022 | [0.32, 0.98] | descriptive |

Models whose rank differs from their M1 rank by 4+ places: glm-5.3-flash (6.7 commands here = rank 8 of 12; M1 3.8 = rank 12) and
granite-4.2-8b (2.3 here = rank 12; M1 8.9 = rank 7). See `N_per_model.csv`.

Regex for "could not finish" checked on 46 final messages (5 per model with a message; gemma and gpt-oss have none
that ended on their own): 39/46 agree (`N_regex_hand_check.csv`). It misses Mistral's phrasing ("is not in the current
directory, please ensure…": 4 of 5 missed) and wrongly matches a hypothetical ("if it doesn't exist I will…"), so
the "could not finish" share is an undercount for Mistral. Descriptive only; not part of the primary test.
