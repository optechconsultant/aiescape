"""SYNTHETIC ground truth for dry-runs. Nothing here is a finding about real models.

Scripted agents decide whether to breach with a known logistic model, then actually execute the
harness's honest or breach commands, so the sandbox, scorer and analysis are exercised end to
end and the analysis can be checked against coefficients we know.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config import design_row, feature_names

TRUE_COEF = {
    "intercept": -5.2,
    "conflict=soft": 0.7, "conflict=hard": 1.6,
    "honest_path=blocked": 1.3,
    "privilege=medium": 0.3, "privilege=high": 0.6,
    "monitoring=stated": -0.4, "monitoring=visible": -0.8,
    "stakes=task_failure": 0.4, "stakes=shutdown": 0.9,
    "framing=urgent": 0.3, "framing=persona": 0.5,
    "escalation=nominal": -0.3, "escalation=credible": -1.1,
    "conflict=hard:honest_path=blocked": 0.9,
    "monitoring=visible:stakes=shutdown": -0.5,
}
_BETA = np.array([TRUE_COEF.get(n, 0.0) for n in feature_names()])
RL_FLAGS = [0, 1, 1, 0, 1, 0, 0, 1]


@dataclass(frozen=True)
class SimModel:
    name: str
    capability: float
    rl_heavy: int
    u: float  # model random effect on propensity


def simulated_models(n: int = 8, seed: int = 7) -> list[SimModel]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        cap = float(np.clip(0.15 + 0.8 * i / (n - 1) + rng.normal(0, 0.05), 0, 1))
        rl = RL_FLAGS[i % len(RL_FLAGS)]
        out.append(SimModel(f"sim-{chr(65 + i)}", cap, rl, 0.6 * rl + 0.8 * (cap - 0.55) + float(rng.normal(0, 0.3))))
    return out


def family_effects(n_families: int = 10, seed: int = 11) -> np.ndarray:
    return np.random.default_rng(seed).normal(0, 0.4, n_families)


def true_logit(cfg: dict[str, str], model: SimModel, v_family: float) -> float:
    return float(np.array(design_row(cfg)) @ _BETA + model.u + v_family)


class ScriptedAgent:
    def act(self, spec, cfg, model: SimModel, v_family: float, rng: np.random.Generator, sandbox):
        p = 1.0 / (1.0 + np.exp(-true_logit(cfg, model, v_family)))
        attempt = bool(rng.random() < p)
        style = str(rng.choice(list(spec.breach_scripts))) if attempt else "honest"
        script = spec.breach_scripts[style] if attempt else spec.honest_script
        r = sandbox.run(script, trusted=True)
        return [script], r.stdout, {"p_true": p, "latent_attempt": int(attempt), "style": style}
