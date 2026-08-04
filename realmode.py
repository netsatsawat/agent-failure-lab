#!/usr/bin/env python3
"""Real mode CLI: run an actual local-model agent and report its failures.

Examples:
  python realmode.py run --docs 8 --model qwen3.6:27b
  python realmode.py run --docs 8 --mitigation retry
  python realmode.py run --mock --inject categorize=garbage
  python realmode.py report runs/qwen3.6-27b_none.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from failure_lab.realmode.llm import MockClient, OllamaClient  # noqa: E402
from failure_lab.realmode.report import (  # noqa: E402
    aggregate, load_run, render_report, taxonomy_chart,
)
from failure_lab.realmode.runner import run_experiment  # noqa: E402


def cmd_run(args) -> None:
    if args.mock:
        inject = dict(kv.split("=") for kv in args.inject)
        client = MockClient(inject=inject,
                            fail_first_attempt_only=args.fail_first_only)
        model_label = "mock"
    else:
        client = OllamaClient(model=args.model)
        model_label = args.model.replace(":", "-").replace("/", "-")
    suffix = "_hard" if args.hard else ""
    out = ROOT / "runs" / f"{model_label}_{args.mitigation}{suffix}.jsonl"
    print(f"running {args.docs} docs × 8 steps · model={model_label} · "
          f"mitigation={args.mitigation} · hard={args.hard}\n→ {out}", flush=True)
    summary = run_experiment(client, n_docs=args.docs,
                             mitigation=args.mitigation, seed=args.seed,
                             out_path=out, label=model_label, hard=args.hard)
    print(f"\nend-to-end success: {summary['end_to_end_rate']:.0%}")
    _report(out, model_label, args.mitigation, args.hard)


def cmd_show_doc(args) -> None:
    """Print a generated document and its ground truth, exactly as a run sees it."""
    import random

    from failure_lab.realmode.documents import make_ground_truth, render_document

    rng = random.Random(args.seed)
    gt = doc = None
    for doc_id in range(1, args.doc_id + 1):  # consume rng like the runner does
        gt = make_ground_truth(doc_id, rng)
        doc = render_document(gt, rng, hard=args.hard)
    print(doc)
    print("\n--- ground truth (what the agent is graded against) ---")
    print(f"trip: {gt.start} to {gt.end} · {len(gt.items)} claimable items")
    for i in gt.items:
        print(f"  {i.description}: {i.amount} {i.currency} "
              f"= {i.amount_usd} USD ({i.category})")
    print(f"grand total: {gt.grand_total} USD · "
          f"flags: {', '.join(gt.true_flag_names) or 'none'}")


def cmd_report(args) -> None:
    path = Path(args.run_file)
    stem = path.stem
    hard = stem.endswith("_hard")
    if hard:
        stem = stem[: -len("_hard")]
    model, _, mitigation = stem.rpartition("_")
    if mitigation not in ("none", "retry", "verify"):
        model, mitigation = stem, "?"
    _report(path, model or stem, mitigation, hard)


def _report(run_path: Path, model: str, mitigation: str,
            hard: bool = False) -> None:
    try:
        agg = aggregate(load_run(run_path))
    except ValueError as e:
        sys.exit(f"error: {run_path}: {e}")
    png = run_path.with_suffix(".png")
    md = run_path.with_suffix(".md")
    taxonomy_chart(agg, png)
    render_report(agg, {"model": model, "mitigation": mitigation,
                        "hard": hard}, md, png.name)
    print(f"report: {md}\nchart:  {png}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the experiment")
    r.add_argument("--docs", type=int, default=8)
    r.add_argument("--model", default="qwen3.6:27b")
    r.add_argument("--mitigation", choices=("none", "retry", "verify"),
                   default="none")
    r.add_argument("--seed", type=int, default=42)
    r.add_argument("--hard", action="store_true",
                   help="adversarial documents: scan noise, a VOIDED line, "
                        "a wrong printed total")
    r.add_argument("--mock", action="store_true",
                   help="use the oracle mock instead of a real model")
    r.add_argument("--inject", nargs="*", default=[],
                   help="mock failure injection, e.g. categorize=garbage")
    r.add_argument("--fail-first-only", action="store_true",
                   help="injected failures succeed on retry")
    r.set_defaults(func=cmd_run)

    p = sub.add_parser("report", help="rebuild report from a JSONL run")
    p.add_argument("run_file")
    p.set_defaults(func=cmd_report)

    d = sub.add_parser("show-doc",
                       help="print a generated document + its ground truth")
    d.add_argument("--doc-id", type=int, default=1)
    d.add_argument("--seed", type=int, default=42)
    d.add_argument("--hard", action="store_true")
    d.set_defaults(func=cmd_show_doc)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
