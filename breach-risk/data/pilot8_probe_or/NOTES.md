# pilot8 OpenRouter probes (Amendment 8 §3): 3 throwaway runs per model, not analysed

Host openrouter.ai, every call pinned to the DeepInfra endpoint in `models.pilot8.json`; `providers` = DeepInfra on
every completed call. Keys: first 3 jobs per model in the seeded order (`throwaway.txt`). Image rebuilt with
`build_image_host.sh` (new image ID, same procedure); httpx loaded from the local uv cache via PYTHONPATH (no PyPI).

| model | result |
| --- | --- |
| ling-3.0-flash | 3/3 structured tool calls |
| granite-4.2-8b | 3/3 structured tool calls |
| minimax-m3 | 3/3 structured tool calls -> **passes, replaces Seed-2.0-mini** |
| glm-5.3-flash | 3/3 (one run first failed with a single DeepInfra 502 timeout relayed by OpenRouter; resumed run completed; not repeated) |
| gpt-oss-120b (bf16) | 3/3 structured tool calls; 2 runs ended after one `ls -R` with an empty final message (no text tool calls) |

All five pass the Amendment 7 §2 rule. `probe48.txt` lists the 240 probe-set keys (Amendment 7 §1) run first.
