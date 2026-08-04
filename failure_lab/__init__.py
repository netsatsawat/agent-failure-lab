"""agent-failure-lab: compound-failure math for multi-step AI agents."""

from failure_lab.model import (
    MITIGATIONS,
    chain_success,
    effective_step_p,
    expected_calls,
    expected_calls_per_step,
    required_step_accuracy,
    simulate_chain,
)

__all__ = [
    "MITIGATIONS",
    "chain_success",
    "effective_step_p",
    "expected_calls",
    "expected_calls_per_step",
    "required_step_accuracy",
    "simulate_chain",
]
