"""Deterministic tests for real mode, using the oracle mock (no model needed).

Run: python tests/test_realmode.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from failure_lab.realmode.agent import STEPS
from failure_lab.realmode.llm import MockClient
from failure_lab.realmode.report import aggregate
from failure_lab.realmode.runner import run_experiment


def rates(summary, step):
    recs = [r for r in summary["records"] if r["step"] == step]
    return {o: sum(r["outcome"] == o for r in recs) / len(recs)
            for o in ("success", "wrong_value", "format_error", "tool_error")}


class FlakyClient(MockClient):
    """Oracle mock whose transport dies for one document (infra_error)."""

    def __init__(self, dead_doc: int, **kw):
        super().__init__(**kw)
        self.dead_doc = dead_doc
        self._doc = 0

    def begin_doc(self, doc_id: int) -> None:
        super().begin_doc(doc_id)
        self._doc = doc_id

    def complete(self, prompt: str) -> str:
        if self._doc == self.dead_doc:
            raise RuntimeError("connection refused")
        return super().complete(prompt)


def test_oracle_is_perfect():
    s = run_experiment(MockClient(), n_docs=5, verbose=False)
    assert s["end_to_end_rate"] == 1.0, s["end_to_end_rate"]
    for step in ("extract_dates", "extract_items", "categorize", "request_rates",
                 "convert_amounts", "sum_categories", "policy_check",
                 "final_summary"):
        assert rates(s, step)["success"] == 1.0, (step, rates(s, step))


def test_hard_mode_keeps_ground_truth_intact():
    # Hard rendering adds noise/traps to the DOCUMENT only; the oracle answers
    # from ground truth must still make a perfect run.
    s = run_experiment(MockClient(), n_docs=4, verbose=False, hard=True)
    assert s["end_to_end_rate"] == 1.0, s["end_to_end_rate"]


def test_garbage_is_format_error_and_kills_e2e():
    s = run_experiment(MockClient(inject={"categorize": "garbage"}),
                       n_docs=4, verbose=False)
    assert rates(s, "categorize")["format_error"] == 1.0
    assert s["end_to_end_rate"] == 0.0
    # Downstream steps keep working thanks to oracle substitution:
    assert rates(s, "sum_categories")["success"] == 1.0


def test_retry_recovers_transient_format_error():
    s = run_experiment(MockClient(inject={"categorize": "garbage"},
                                  fail_first_attempt_only=True),
                       n_docs=4, mitigation="retry", verbose=False)
    assert rates(s, "categorize")["success"] == 1.0
    assert s["end_to_end_rate"] == 1.0
    retried = [r for r in s["records"]
               if r["step"] == "categorize" and r["attempts"] == 2]
    assert len(retried) == 4


def test_wrong_tool_is_tool_error():
    s = run_experiment(MockClient(inject={"request_rates": "wrong_tool"}),
                       n_docs=3, verbose=False)
    assert rates(s, "request_rates")["tool_error"] == 1.0
    assert s["end_to_end_rate"] == 0.0


def test_wrong_value_is_not_recovered_by_retry():
    s = run_experiment(MockClient(inject={"convert_amounts": "wrong_value"}),
                       n_docs=3, mitigation="retry", verbose=False)
    assert rates(s, "convert_amounts")["wrong_value"] == 1.0
    # wrong values propagate (no substitution) and poison the end result
    assert s["end_to_end_rate"] == 0.0
    # retry must NOT have fired: wrong_value is not code-detectable
    assert all(r["attempts"] == 1 for r in s["records"]
               if r["step"] == "convert_amounts")


def test_verifier_catches_wrong_value_and_buys_retry():
    # First attempt at convert_amounts is corrupted; the blind verifier flags
    # it; the corrected attempt succeeds. This is the mitigation retry can't be.
    s = run_experiment(
        MockClient(inject={"convert_amounts": "wrong_value"},
                   fail_first_attempt_only=True,
                   verifier_verdicts={"convert_amounts": ["fail"]}),
        n_docs=3, mitigation="verify", verbose=False)
    assert rates(s, "convert_amounts")["success"] == 1.0
    assert s["end_to_end_rate"] == 1.0
    recs = [r for r in s["records"] if r["step"] == "convert_amounts"]
    assert all(r["attempts"] == 2 and r["verifier_flags"] == 1 for r in recs)


def test_verifier_pass_leaves_results_untouched():
    s = run_experiment(MockClient(), n_docs=3, mitigation="verify",
                       verbose=False)
    assert s["end_to_end_rate"] == 1.0
    checked = [r for r in s["records"] if r["step"] != "__end_to_end__"]
    assert all(r["verifier_checks"] == 1 and r["verifier_flags"] == 0
               for r in checked)


def test_infra_document_is_excluded_from_per_step_rates():
    # Doc 2 loses transport at step 3 and is wrong on every other step. The
    # report says infra-affected documents are excluded from the metrics, so
    # none of those wrong values may reach a per-step rate: all rates stay 1.0.
    steps = [s[0] for s in STEPS]
    records = [{"doc_id": 1, "step": s, "outcome": "success", "attempts": 1}
               for s in steps]
    records.append({"doc_id": 1, "step": "__end_to_end__", "outcome": "success",
                    "infra_affected": False, "attempts": 0})
    records += [{"doc_id": 2, "step": s, "attempts": 1,
                 "outcome": "infra_error" if i == 2 else "wrong_value"}
                for i, s in enumerate(steps)]
    records.append({"doc_id": 2, "step": "__end_to_end__", "outcome": "failure",
                    "infra_affected": True, "attempts": 0})
    agg = aggregate(records)
    assert agg["n_docs"] == 1 and agg["infra_docs"] == 1
    assert agg["observed_e2e"] == 1.0
    assert all(v == 1.0 for v in agg["step_rates"].values()), agg["step_rates"]
    assert "wrong_value" not in agg["per_step"][steps[0]]
    # the transport failure itself stays visible in the infra error column
    assert agg["per_step"][steps[2]]["infra_error"] == 1


def test_runner_and_report_agree_when_a_document_hits_infra():
    s = run_experiment(FlakyClient(dead_doc=3), n_docs=4, verbose=False)
    assert s["infra_docs"] == 1 and s["scored_docs"] == 3
    # one number for one run: the JSON summary and the markdown report must
    # divide by the same thing.
    assert s["end_to_end_rate"] == aggregate(s["records"])["observed_e2e"] == 1.0


def test_extract_json_is_string_aware():
    from failure_lab.realmode.agent import extract_json
    assert extract_json('Here is {the result}: {"items": []}') == {"items": []}
    assert extract_json('{"reason": "matched } brace", "ok": true}') == {
        "reason": "matched } brace", "ok": True}
    assert extract_json("no json here at all") is None


def test_duplicate_items_are_wrong_value():
    from failure_lab.realmode.agent import _e_extract_items
    oracle = {"items": [{"description": "A", "amount": 1.0, "currency": "USD"}]}
    dup = {"items": [{"description": "A", "amount": 1.0, "currency": "USD"},
                     {"description": "A", "amount": 1.0, "currency": "USD"}]}
    outcome, detail = _e_extract_items({}, dup, oracle)
    assert outcome == "wrong_value", (outcome, detail)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
