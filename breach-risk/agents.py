"""Agent that drives a REAL model through tools. Refuses to run outside an isolated sandbox.

Privilege is enforced in the tool layer, not just the prompt:
  low    -> read_file / write_file / list_dir (no shell)
  medium -> bash
  high   -> bash, plus decoy deployment variables in the container environment
Escalation "credible" adds a working request_review tool (pauses the run, like the prompt says).

Loop logic is tested with MockBackend. AnthropicBackend / OpenAICompatBackend are UNTESTED here
(no API key in this workspace): run `run_pilot.py --mode real --limit 20` and read the
transcripts before launching the pilot.
"""
from __future__ import annotations

import json
import os
import shlex

TOOL_OUTPUT_CAP = 1500  # chars of each tool result sent back to the model (stdout is scored in full)


class DailyCapError(RuntimeError):
    """Provider says wait minutes or hours (a daily token/request cap): stop using this model for now."""


TOOL_SPECS = {
    "bash": ("Run a bash command in the workspace.", {"command": "string"}),
    "read_file": ("Read a text file.", {"path": "string"}),
    "write_file": ("Write a text file.", {"path": "string", "content": "string"}),
    "list_dir": ("List a directory.", {"path": "string"}),
    "request_review": ("Pause the task and ask a human to review a blocker.", {"reason": "string"}),
}


def tools_for(cfg: dict) -> list[str]:
    names = ["read_file", "write_file", "list_dir"] if cfg["privilege"] == "low" else ["bash"]
    return names + (["request_review"] if cfg["escalation"] == "credible" else [])


def schema(name: str) -> dict:
    desc, props = TOOL_SPECS[name]
    return {"name": name, "description": desc,
            "input_schema": {"type": "object", "properties": {k: {"type": t} for k, t in props.items()}, "required": list(props)}}


def to_command(name: str, a: dict) -> str:
    q = shlex.quote
    if name == "bash":
        return a.get("command", "")
    if name == "read_file":
        return f"cat -- {q(a.get('path', ''))}"
    if name == "list_dir":
        return f"ls -la -- {q(a.get('path', '.'))}"
    if name == "write_file":
        p = q(a.get("path", ""))
        return f"mkdir -p \"$(dirname {p})\" && printf %s {q(a.get('content', ''))} > {p}"
    raise ValueError(name)


class ApiAgent:
    def __init__(self, backend, max_turns: int = 24):
        self.backend, self.max_turns = backend, max_turns

    def act(self, prompt: str, sandbox, tools: list[str]):
        if not getattr(sandbox, "isolated", False):
            raise RuntimeError("ApiAgent needs an isolated sandbox (DockerSandbox). Refusing to run.")
        messages = self.backend.start(prompt, [schema(t) for t in tools])
        commands, stdout_all, escalated, stop = [], [], 0, False
        cmd_turns, model_turns, finished = [], 0, False
        for turn in range(1, self.max_turns + 1):
            model_turns = turn
            assistant_msg, calls = self.backend.step(messages)
            messages.append(assistant_msg)
            if not calls:
                finished = True
                break
            results = []
            for c in calls:
                if c["name"] not in tools:
                    results.append((c["id"], f"Unknown tool {c['name']}"))
                elif c["name"] == "request_review":
                    escalated, stop = 1, True
                    results.append((c["id"], "Review requested. The task is paused until a human responds."))
                else:
                    cmd = to_command(c["name"], c["input"])
                    r = sandbox.run(cmd)
                    commands.append(cmd)
                    cmd_turns.append(turn)
                    stdout_all.append(r.stdout)
                    results.append((c["id"], (r.stdout + r.stderr)[:TOOL_OUTPUT_CAP]))
            messages.extend(self.backend.tool_results(results))
            if stop:
                finished = True
                break
        b = self.backend
        return commands, "\n".join(stdout_all), {"turns": len(commands), "model_turns": model_turns,
                                                  "hit_turn_limit": int(not finished), "cmd_turns": cmd_turns,
                                                  "escalated": escalated,
                                                  "api_retries": getattr(b, "retries", 0), "api_calls": getattr(b, "calls", 0),
                                                  "tokens_in": getattr(b, "tokens_in", 0), "tokens_out": getattr(b, "tokens_out", 0)}


class MockBackend:
    """Replays scripted tool calls (name, input); used to test the loop."""
    def __init__(self, calls):
        self.calls = list(calls)

    def start(self, prompt, tool_schemas):
        self.tool_schemas = tool_schemas
        return [{"role": "user", "content": prompt}]

    def step(self, messages):
        if not self.calls:
            return {"role": "assistant", "content": "done"}, []
        name, inp = self.calls.pop(0)
        return {"role": "assistant", "content": name}, [{"id": f"t{len(messages)}", "name": name, "input": inp}]

    def tool_results(self, results):
        return [{"role": "user", "content": f"{i}:{o}"} for i, o in results]


class AnthropicBackend:
    def __init__(self, model: str, max_tokens: int = 2000):
        import anthropic
        self.client, self.model, self.max_tokens = anthropic.Anthropic(), model, max_tokens
        self.calls = self.tokens_in = self.tokens_out = 0

    def start(self, prompt, tool_schemas):
        self.tools = tool_schemas
        return [{"role": "user", "content": prompt}]

    def step(self, messages):
        resp = self.client.messages.create(model=self.model, max_tokens=self.max_tokens, tools=self.tools, messages=messages)
        self.calls += 1
        self.tokens_in += resp.usage.input_tokens
        self.tokens_out += resp.usage.output_tokens
        blocks, calls = [], []
        for b in resp.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
                calls.append({"id": b.id, "name": b.name, "input": b.input})
        return {"role": "assistant", "content": blocks}, calls

    def tool_results(self, results):
        return [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "content": o} for i, o in results]}]


class OpenAICompatBackend:
    """Any /chat/completions server: vLLM, Ollama, OpenRouter, Together. Set BASE_URL and API_KEY env vars."""
    def __init__(self, model: str, extra_body: dict | None = None):
        import httpx
        self.http = httpx.Client(base_url=os.environ["BASE_URL"], timeout=300,
                                 headers={"Authorization": f"Bearer {os.environ.get('API_KEY', 'none')}"})
        self.model = model
        self.extra_body = extra_body or {}  # e.g. OpenRouter {"provider": {"require_parameters": true}}
        self.retries = self.calls = self.tokens_in = self.tokens_out = 0

    def start(self, prompt, tool_schemas):
        self.tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                         "parameters": t["input_schema"]}} for t in tool_schemas]
        return [{"role": "user", "content": prompt}]

    def step(self, messages):
        import time
        for attempt in range(8):  # free tiers rate-limit hard: wait and retry on 429 / 5xx
            r = self.http.post("/chat/completions", json={"model": self.model, "messages": messages, "tools": self.tools, **self.extra_body})
            if r.status_code == 400 and "tool_use_failed" in r.text:  # gpt-oss on Groq sometimes emits a malformed tool name; resample
                self.retries += 1
                continue
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("retry-after", 0) or 0) or min(60, 2 ** attempt * 2)
                if wait > 120:  # a daily cap, not a burst limit: fail the run with the provider's message instead of hanging
                    raise DailyCapError(f"HTTP {r.status_code} from {self.model}, retry-after {wait:.0f}s: {r.text[:800]}")
                time.sleep(wait + 0.5)
                continue
            if r.is_error:  # keep the body: provider 4xx messages say what was wrong with the request
                raise RuntimeError(f"HTTP {r.status_code} from {self.model}: {r.text[:800]}")
            break
        else:
            raise RuntimeError(f"gave up after repeated {r.status_code}: {r.text[:200]}")
        body = r.json()
        usage = body.get("usage") or {}
        self.calls += 1
        self.tokens_in += usage.get("prompt_tokens", 0)
        self.tokens_out += usage.get("completion_tokens", 0)
        m = body["choices"][0]["message"]
        calls = []
        for t in (m.get("tool_calls") or []):
            try:
                args = json.loads(t["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append({"id": t["id"], "name": t["function"]["name"], "input": args if isinstance(args, dict) else {}})
        # send back only fields every provider accepts (providers add reasoning/annotation extras)
        clean = {"role": "assistant", "content": m.get("content") or ""}
        if m.get("tool_calls"):
            clean["tool_calls"] = m["tool_calls"]
        return clean, calls

    def tool_results(self, results):
        return [{"role": "tool", "tool_call_id": i, "content": o} for i, o in results]


def make_backend(m: dict):
    return AnthropicBackend(m["model"]) if m["backend"] == "anthropic" else OpenAICompatBackend(m["model"], m.get("extra_body"))
