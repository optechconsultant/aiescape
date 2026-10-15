# pilot7 probes (throwaway, not analysed; Amendment 4 §2)
3 runs per candidate, DeepInfra, image sha256:a127b4e4… (rebuilt with build_image_host.sh in a fresh container).
Harness note: httpx loaded from the uv cache via PYTHONPATH (as in pilot6's run log); the first two probe attempts
failed on import and were discarded (no API calls made).

| candidate | DeepInfra ID | quant | tool calls | result |
| --- | --- | --- | --- | --- |
| deepseek-v4-flash | deepseek-ai/DeepSeek-V4-Flash-0731 | fp8 | 3/3 structured | pass |
| gemma-4-26b-a4b | google/gemma-4-26B-A4B-it | fp8 | 3/3 | pass |
| gpt-oss-120b | openai/gpt-oss-120b-Ultra | fp8 | 3/3 | pass |
| mimo-v2.6-flash | XiaomiMiMo/MiMo-V2.6-Flash | fp8 | 3/3 | pass |
| llama-3.3-70b | meta-llama/Llama-3.3-70B-Instruct-Turbo | fp8 | 1/3: two runs wrote `<function=bash{...}>` as text | FAIL |
| llama-4-scout | meta-llama/Llama-4-Scout-17B-16E-Instruct | fp8 | 3/3 (weak at the task) | pass |
| nemotron-3-super | nvidia/NVIDIA-Nemotron-3-Super-120B-A12B | bf16 (no fp8) | 1 run finished of 6 tries; rest 429 "Model busy" | FAIL (capacity) |
| nemotron-3.5-lightning | nvidia/NVIDIA-Nemotron-3.5-Lightning | not stated by DeepInfra | 3/3 | pass |
