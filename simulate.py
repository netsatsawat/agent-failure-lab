#!/usr/bin/env python3
"""Compound-failure simulator: why 85% per-step accuracy collapses end to end.

Companion code for the book "Why Your AI Agent Will Fail" and the article
"The Math That's Killing Your AI Agent" (satsawat.ai). Stdlib only.

Usage: python simulate.py [--accuracy 0.85] [--steps 10] [--trials 20000]
"""

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from failure_lab.model import (  # noqa: E402
    DEFAULT_VERIFIER_RECALL,
    MITIGATIONS,
    chain_success,
    expected_calls,
    simulate_chain,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compound-failure simulator for multi-step AI agents.")
    parser.add_argument("--accuracy", type=float, default=0.85,
                        help="per-step success rate (default: 0.85)")
    parser.add_argument("--steps", type=int, default=10,
                        help="maximum chain length (default: 10)")
    parser.add_argument("--trials", type=int, default=20000,
                        help="Monte Carlo trials per cell (default: 20000)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not 0 < args.accuracy <= 1:
        parser.error("--accuracy must be in (0, 1]")

    rng = random.Random(args.seed)
    recall = DEFAULT_VERIFIER_RECALL

    print(f"\nPer-step accuracy: {args.accuracy:.0%}   "
          f"trials per cell: {args.trials}")
    print(f"verify = {recall:.0%}-recall LLM verifier + one corrected attempt "
          f"· retry = one retry on code-detectable failures\n")

    header = f"{'steps':>5} | " + " | ".join(f"{m:^16}" for m in MITIGATIONS)
    print(header)
    print("-" * len(header))
    for n in range(1, args.steps + 1):
        cells = []
        for m in MITIGATIONS:
            analytic = chain_success(args.accuracy, n, m, recall)
            mc = simulate_chain(args.accuracy, n, m, args.trials, rng, recall)
            cells.append(f"{analytic:6.1%} ({mc.success_rate:5.1%})")
        print(f"{n:>5} | " + " | ".join(f"{c:^16}" for c in cells))
    print("\nformat: analytic (simulated)")

    n = args.steps
    costs = " · ".join(
        f"{m} {expected_calls(args.accuracy, n, m, recall):.1f}"
        for m in MITIGATIONS)
    print(f"expected LLM calls for the {n}-step chain: {costs}\n")


if __name__ == "__main__":
    main()
