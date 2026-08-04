"""Experiment loop: N documents through the chain, JSONL log per run."""

from __future__ import annotations

import json
import random
from pathlib import Path

from failure_lab.realmode.agent import run_chain
from failure_lab.realmode.documents import make_ground_truth, render_document


def run_experiment(client, n_docs: int = 8, mitigation: str = "none",
                   seed: int = 42, out_path: Path | None = None,
                   label: str = "run", verbose: bool = True,
                   hard: bool = False) -> dict:
    rng = random.Random(seed)
    lines = []
    e2e_ok = 0
    f = None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(out_path, "w")
    try:
        for doc_id in range(1, n_docs + 1):
            gt = make_ground_truth(doc_id, rng)
            doc = render_document(gt, rng, hard=hard)
            if hasattr(client, "begin_doc"):
                client.begin_doc(doc_id)
            records, ok, infra_affected = run_chain(client, doc, gt, mitigation)
            e2e_ok += ok
            doc_lines = [{"doc_id": doc_id, "mitigation": mitigation, **r}
                         for r in records]
            doc_lines.append({"doc_id": doc_id, "mitigation": mitigation,
                              "step": "__end_to_end__",
                              "outcome": "success" if ok else "failure",
                              "infra_affected": infra_affected,
                              "attempts": 0, "detail": "", "latency_s": 0})
            lines.extend(doc_lines)
            if f:  # stream results per document so long runs are inspectable
                for line in doc_lines:
                    f.write(json.dumps(line) + "\n")
                f.flush()
            if verbose:
                steps_str = " ".join(
                    {"success": "✓", "wrong_value": "V", "format_error": "F",
                     "tool_error": "T", "infra_error": "I"}[r["outcome"]]
                    for r in records)
                print(f"doc {doc_id:>2}/{n_docs}  [{steps_str}]  "
                      f"end-to-end: {'OK' if ok else 'FAIL'}", flush=True)
    finally:
        if f:
            f.close()
    return {"label": label, "n_docs": n_docs, "mitigation": mitigation,
            "end_to_end_rate": e2e_ok / n_docs, "records": lines,
            "out_path": str(out_path) if out_path else None}
