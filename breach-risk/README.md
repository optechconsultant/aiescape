# Breach-risk pilot harness

Predicts whether an LLM agent will step outside a rule, from information known before deployment
(goal conflict, honest path, privileges, monitoring, stakes, framing, escalation, model traits).

## Status

| Part | Status |
| --- | --- |
| 48-run D-optimal design (7 factors, 1,458-cell grid) | Tested: full rank 20/20, balanced, D-efficiency 0.130 vs best random 0.114 |
| 10 scenario families, canary-file breach scorer | Tested on 7,680 scripted runs: 638/638 breaches caught (6 techniques incl. base64 and silent copy), 0 false positives |
| Analysis (held-out validation, calibration, effects) | Tested on SYNTHETIC data only |
| Agent loop, privilege-based tool sets, request_review tool, safety guards | Tested with a mock model |
| `DockerSandbox`, `AnthropicBackend`, `OpenAICompatBackend` | NOT tested (no image registry or API key in the build workspace) |

## Dry run (already done, synthetic)

```
python run_pilot.py --mode dryrun --seeds 2 --out data/dryrun_synthetic
python analysis.py data/dryrun_synthetic/runs.csv
```
Scripted agents breach with a known logistic probability. It proves the machinery works and the
analysis recovers known effects. It says NOTHING about real models.

## Real pilot (needs a machine with Docker + image pulls + model access)

1. `pip install inspect-ai anthropic httpx pandas numpy scipy scikit-learn statsmodels`
2. `docker build -t breach-agent:latest .`
3. Copy `models.example.json` to `models.json` and fill it in. `rl_heavy` and `capability` are model
   facts YOU supply; take `capability` from a SandboxEscapeBench score. Keys go in environment
   variables (`ANTHROPIC_API_KEY`; `BASE_URL` and `API_KEY` for OpenAI-compatible servers). Never in files or chat.
4. Smoke test, then READ the transcripts before going further:
   `python run_pilot.py --mode real --limit 20 --workers 2 --out data/pilot`
   Open `data/pilot/transcripts.jsonl`. Check that tools work, breaches are real, and no run escapes the container.
5. Pilot (500 runs), measure the real base rate, then scale. Runs resume if interrupted.
6. `python analysis.py data/pilot/runs.csv` (on real data it prints effect estimates with intervals; the "truth" comparison only appears for synthetic runs)

## Safety rules built in

- `ApiAgent` refuses any sandbox that is not isolated; `LocalSandbox` refuses any command a model wrote.
- Containers: no network, all capabilities dropped, no-new-privileges, 256 PIDs, 512 MB, deleted after each run.
- The restricted resource is a text file with a random token. Nothing here probes kernel or runtime escapes.

## Known limits

- This suite measures propensity (will it step outside a rule). The capability term (can it escape)
  needs SandboxEscapeBench environments, which need Docker image access.
- The scorer was validated against harness-written breach techniques. Real models may invent others
  (for example read the file into a variable and never print it). Human-audit all negatives you doubt.
- Evaluation awareness is not yet measured. Add a "does the transcript say this is a test" flag.

## Running with Groq (free tier)

```
export BASE_URL=https://api.groq.com/openai/v1
export API_KEY=<your Groq key>          # in your shell only, never in a file
python run_pilot.py --mode real --models-file models.groq.json --limit 20 --workers 1 --out data/pilot
```
- `models.groq.json` has gpt-oss-120b and gpt-oss-20b. `capability` there is a PLACEHOLDER ordering (120b above 20b),
  not a measured score; replace it before any cross-model analysis.
- The connector waits and retries on HTTP 429 (tested against a fake server, not yet against Groq itself).
- Free-tier limits are tight. Start with `--workers 1`. Check your real limits at console.groq.com before
  scaling, because the full 7,680-run design will not fit a free daily token budget.
