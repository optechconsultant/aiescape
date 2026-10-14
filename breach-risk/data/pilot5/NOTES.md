# pilot5 (OpenRouter, 5 open-weight models): notes

Date: 2026-10-14. Rule: Preregistration Amendment 1 + Clarification 1 (`report_amended.txt`); original rule
in `report.txt` for comparison. 100 runs: per model 15 high-pressure (cfg 43/44) + 5 low-pressure (cfg 0-7), 24-turn limit.

## Models and pinned providers (OpenRouter `provider.only` + `allow_fallbacks: false`, `require_parameters: true`)
All five IDs in `models.openrouter.json` existed in `GET /api/v1/models?supported_parameters=tools`; none replaced.

| model | OpenRouter ID | provider (every call) |
| --- | --- | --- |
| llama-3.1-8b | meta-llama/llama-3.1-8b-instruct | Groq |
| llama-3.3-70b | meta-llama/llama-3.3-70b-instruct | Together (DeepInfra-turbo returned empty messages; CoreWeave printed tool JSON as text) |
| mistral-small-3.2 | mistralai/mistral-small-3.2-24b-instruct | DeepInfra fp8 |
| deepseek-v3.1 | deepseek/deepseek-chat-v3.1 | SiliconFlow fp8 (DeepInfra serves fp4) |
| qwen3-235b | qwen/qwen3-235b-a22b-2507 | DeepInfra fp8 |

`providers` in `runs.jsonl` records the provider OpenRouter reported for each run; every run had exactly one.
`max_tokens: 4096` is set for all models (without it OpenRouter reserved the full context and refused with 402).

## Sample
Jobs are the first 15 (cfg 43/44) and first 5 (cfg 0-7) of the seeded shuffle (`--master-seed 2026`), which is
what a single `--limit 15` / `--limit 5` call selects (`pilot5_order.py`). Because the runs were launched in two
batches, Llama runs past position 15 were also executed; they and all failed attempts (connection resets, HTTP 402
"in-flight credits") are in `runs_excluded.jsonl` / `transcripts_excluded.jsonl` and are NOT in the reports.
Throwaway tool-calling probes: `data/pilot5_probe/` (3 per model, not analysed).

## Deviations from earlier pilots (environment)
- Docker Hub and PyPI are blocked in this session. The image was built from the host's own Ubuntu 24.04 files
  (`docker import` of /usr/bin, /usr/lib/x86_64-linux-gnu, python3.13), then the same `useradd agent` /
  `/workspace` / `/restricted` layers as `Dockerfile`. Not byte-identical to `python:3.12-slim`: more binaries,
  so root-wide `find /` output is longer. No sudo/su in the image. Same `docker run` isolation flags.
- `httpx` was loaded from a local uv cache.

## Tool calling
- llama-3.1-8b: 13 of 20 runs made NO tool call (it wrote `<bash>...</bash>` or `<request_review>` as plain text,
  which ends the run). Its numbers mostly measure tool-calling failure, not propensity.
- llama-3.3-70b: calls a tool on turn 1, then usually answers with a code block in text (run ends after 1-2 commands).
- mistral, deepseek, qwen: tool calls work.

## Cost
After the first 20 runs: $0.011. Final, 100 counted runs: $0.106 (deepseek $0.060, qwen $0.019, llama-70b $0.018,
mistral $0.009, llama-8b $0.001). Key usage including probes, excluded and failed runs: about $0.15.
