"""Sandboxes.

LocalSandbox  - throwaway directory + subprocess. NOT a security boundary. It only runs
                commands written by this harness (trusted=True), so it can drive scripted
                agents for dry-runs. It refuses any command from a model.
DockerSandbox - the sandbox for real model runs: no network, all capabilities dropped,
                disposable container. UNTESTED here (no image registry reachable).
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    rc: int


class LocalSandbox:
    isolated = False

    def __init__(self, root: Path):
        self.root = root
        self.workspace = root / "workspace"

    def run(self, script: str, trusted: bool = False, timeout: int = 10) -> ExecResult:
        if not trusted:
            raise PermissionError("LocalSandbox is not isolated: it only runs harness-written commands.")
        p = subprocess.run(
            ["bash", "-c", script], cwd=self.workspace, capture_output=True, text=True,
            timeout=timeout, env={"PATH": os.environ["PATH"], "HOME": str(self.root)},
        )
        return ExecResult(p.stdout, p.stderr, p.returncode)

    def workspace_text(self) -> str:
        chunks = []
        for f in self.workspace.rglob("*"):
            if f.is_file():
                try:
                    chunks.append(f.read_text(errors="ignore"))
                except OSError:
                    pass
        return "\n".join(chunks)

    def read_result(self) -> str:
        f = self.workspace / "out" / "result.txt"
        return f.read_text().strip() if f.exists() else ""


class DockerSandbox:
    """Real-run sandbox. Build an image that contains /workspace and /restricted laid out like
    LocalSandbox (see README), then every agent command goes through `docker exec`."""
    isolated = True

    def __init__(self, image: str, env: dict | None = None):
        self.name = None
        self.image = image
        self.env = env or {}

    def __enter__(self):
        out = subprocess.run(
            ["docker", "run", "-d", "--rm", "--network", "none", "--cap-drop", "ALL",
             "--security-opt", "no-new-privileges", "--pids-limit", "256", "--memory", "512m",
             *[x for k, v in self.env.items() for x in ("-e", f"{k}={v}")],
             "-w", "/workspace", self.image, "sleep", "900"],
            capture_output=True, text=True, check=True)
        self.name = out.stdout.strip()
        return self

    def __exit__(self, *exc):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)

    def load(self, root: Path):
        """Copy a run's prepared workspace/ and restricted/ into the container."""
        subprocess.run(["docker", "cp", f"{root}/workspace/.", f"{self.name}:/workspace"], check=True)
        subprocess.run(["docker", "cp", f"{root}/restricted/.", f"{self.name}:/restricted"], check=True)

    def run(self, script: str, trusted: bool = False, timeout: int = 30) -> ExecResult:
        p = subprocess.run(["docker", "exec", "-w", "/workspace", self.name, "bash", "-c", script],
                           capture_output=True, text=True, timeout=timeout)
        return ExecResult(p.stdout, p.stderr, p.returncode)

    def workspace_text(self) -> str:
        p = subprocess.run(["docker", "exec", self.name, "bash", "-c", "cat /workspace/.[!.]* /workspace/* /workspace/out/* 2>/dev/null"],
                           capture_output=True, text=True)
        return p.stdout

    def read_result(self) -> str:
        p = subprocess.run(["docker", "exec", self.name, "cat", "/workspace/out/result.txt"], capture_output=True, text=True)
        return p.stdout.strip()
