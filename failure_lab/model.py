"""Compound-failure model for multi-step AI agents.

The mitigation semantics hinge on *detectability* of a step failure:

- ``none``   : failures go undetected; the chain keeps running and produces a
  confidently wrong result. End-to-end success requires every step to succeed.
- ``retry``  : failures are cheaply detectable (schema validation, tool errors,
  parse failures) at zero LLM cost, and a detected failure gets one retry.
  This is the best case: it only applies to the failure modes you can catch
  with code.
- ``verify`` : failures need an LLM verifier to catch (hallucinations, subtle
  reasoning errors). The verifier costs one extra call per step, detects a
  failure with probability ``verifier_recall``, and a detected failure gets one
  corrected attempt at the base success rate (the correction is not re-verified).

Cost is measured in LLM calls. Because undetected failures do not stop the
chain, every step always executes: expected calls scale linearly with steps.
"""

from __future__ import annotations

from dataclasses import dataclass
import random

MITIGATIONS = ("none", "verify", "retry")

DEFAULT_VERIFIER_RECALL = 0.9


def effective_step_p(p: float, mitigation: str,
                     verifier_recall: float = DEFAULT_VERIFIER_RECALL) -> float:
    """Per-step success probability under a mitigation (analytic)."""
    if mitigation == "none":
        return p
    if mitigation == "retry":
        return 1 - (1 - p) ** 2
    if mitigation == "verify":
        return p + (1 - p) * verifier_recall * p
    raise ValueError(f"unknown mitigation: {mitigation!r}")


def chain_success(p: float, steps: int, mitigation: str = "none",
                  verifier_recall: float = DEFAULT_VERIFIER_RECALL) -> float:
    """Analytic end-to-end success probability for a chain of ``steps`` steps."""
    return effective_step_p(p, mitigation, verifier_recall) ** steps


def required_step_accuracy(target: float, steps: int) -> float:
    """Per-step accuracy required for a target end-to-end success rate."""
    return target ** (1 / steps)


def expected_calls_per_step(p: float, mitigation: str,
                            verifier_recall: float = DEFAULT_VERIFIER_RECALL) -> float:
    """Expected LLM calls per step under a mitigation (analytic)."""
    if mitigation == "none":
        return 1.0
    if mitigation == "retry":
        return 1 + (1 - p)
    if mitigation == "verify":
        return 2 + (1 - p) * verifier_recall
    raise ValueError(f"unknown mitigation: {mitigation!r}")


def expected_calls(p: float, steps: int, mitigation: str = "none",
                   verifier_recall: float = DEFAULT_VERIFIER_RECALL) -> float:
    """Expected LLM calls for the whole chain (analytic)."""
    return steps * expected_calls_per_step(p, mitigation, verifier_recall)


@dataclass
class SimResult:
    success_rate: float
    avg_calls: float


def simulate_chain(p: float, steps: int, mitigation: str = "none",
                   trials: int = 20000, rng: random.Random | None = None,
                   verifier_recall: float = DEFAULT_VERIFIER_RECALL) -> SimResult:
    """Monte Carlo end-to-end success rate and average LLM-call count."""
    rng = rng or random.Random(42)
    successes = 0
    total_calls = 0
    for _ in range(trials):
        chain_ok = True
        for _ in range(steps):
            if mitigation == "none":
                total_calls += 1
                step_ok = rng.random() < p
            elif mitigation == "retry":
                total_calls += 1
                step_ok = rng.random() < p
                if not step_ok:
                    total_calls += 1
                    step_ok = rng.random() < p
            elif mitigation == "verify":
                total_calls += 2
                step_ok = rng.random() < p
                if not step_ok and rng.random() < verifier_recall:
                    total_calls += 1
                    step_ok = rng.random() < p
            else:
                raise ValueError(f"unknown mitigation: {mitigation!r}")
            chain_ok = chain_ok and step_ok
        if chain_ok:
            successes += 1
    return SimResult(successes / trials, total_calls / trials)
