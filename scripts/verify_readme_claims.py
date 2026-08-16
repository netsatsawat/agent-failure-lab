#!/usr/bin/env python3
"""No number in the README without a runnable path behind it.

Four assertions, wired into CI:
1. The analytic headline (end-to-end success at 85% per step over 10 steps)
   must match failure_lab.model.chain_success, recomputed here.
2. Every row of the results table must match the run it describes: the
   committed runs/*.jsonl re-aggregated by failure_lab.realmode.report.aggregate,
   cross-checked against the markdown report committed beside it.
3. The two failures the README narrates by hand (the sum slip on the clean
   run, the conversion error the verifier missed) must be the failures the
   logs actually contain, with both deltas recomputed from the log's own
   detail string rather than quoted back.
4. The reproduction surface the README shows verbatim (the sample document
   from `realmode.py show-doc`, the step count, the model tag and temperature,
   the test count) must match what the code produces today.

Committed artifacts only: no network, no model, no re-run. Stdlib only, which
is what the simulator and the real-mode harness already are.
"""

import importlib.util
import random
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from failure_lab.model import chain_success, expected_calls        # noqa: E402
from failure_lab.realmode.agent import STEPS                       # noqa: E402
from failure_lab.realmode.documents import (                       # noqa: E402
    make_ground_truth, render_document,
)
from failure_lab.realmode.llm import OllamaClient                  # noqa: E402
from failure_lab.realmode.report import aggregate, load_run        # noqa: E402

# The README's results table, in order, each row paired with the run it claims
# to describe. The row label is how the row is found in the README.
TABLE = (
    ("clean documents", "qwen3.6-27b_none.jsonl"),
    ("hard documents", "qwen3.6-27b_none_hard.jsonl"),
    ("clean + `verify`", "qwen3.6-27b_verify.jsonl"),
)

# Inputs, not claims: the headline's parameters and the `show-doc` seed default.
HEADLINE_P, HEADLINE_STEPS = 0.85, 10
SEED = 42

ONES = ("zero", "one", "two", "three", "four", "five", "six", "seven",
        "eight", "nine", "ten")

problems = []


def check(name, condition, detail=""):
    print(f"  {'ok ' if condition else 'FAIL'} {name}" +
          (f" ({detail})" if detail and not condition else ""))
    if not condition:
        problems.append(name)


def table_row(readme, label):
    """The README results-table line whose first cell is ``label``."""
    for line in readme.splitlines():
        if line.startswith("|") and line.split("|")[1].strip() == label:
            return line
    return ""


def per_step_counts(agg):
    """Successes and scored attempts, on aggregate's own denominator: infra
    errors are transport, not model quality, so they leave the denominator."""
    ok = sum(row.get("success", 0) for row in agg["per_step"].values())
    scored = sum(sum(row.values()) - row.get("infra_error", 0)
                 for row in agg["per_step"].values())
    return ok, scored


def only_failure(records):
    """The step attempts in a run that did not succeed (end-to-end rows are a
    verdict on the document, not a step, so they are not failures here)."""
    return [r for r in records
            if r["step"] != "__end_to_end__" and r["outcome"] != "success"]


def two_numbers(text):
    """The last two decimals in a classifier detail string, as floats."""
    found = re.findall(r"\d+\.\d+", text)
    return (float(found[-2]), float(found[-1])) if len(found) >= 2 else (0.0, 0.0)


def main() -> int:
    readme = (REPO / "README.md").read_text(encoding="utf-8")

    print("analytic headline, recomputed from failure_lab.model:")
    # Read the headline's INPUTS out of the README too. Hardcoding them here let
    # the sentence change its own premise ("12 steps at 90%") while the 19.7%
    # output it introduces stayed green.
    stated = re.search(r"Chain (\d+) steps at (\d+)% per-step accuracy", readme)
    check("README states the headline's own parameters", stated is not None)
    steps = int(stated.group(1)) if stated else HEADLINE_STEPS
    p = int(stated.group(2)) / 100 if stated else HEADLINE_P
    check(f"the headline's parameters are the ones this file recomputes "
          f"({p}, {steps})", (p, steps) == (HEADLINE_P, HEADLINE_STEPS),
          f"README says {p} and {steps}")
    headline = chain_success(p, steps)
    check(f"README quotes chain_success({p}, {steps}) "
          f"as {headline:.1%}", f"**{headline:.1%}**" in readme,
          f"{headline:.1%}")
    retry_p = chain_success(p, steps, "retry")
    verify_p = chain_success(p, steps, "verify")
    retry_c = expected_calls(p, steps, "retry")
    verify_c = expected_calls(p, steps, "verify")
    # Assert the README's SENTENCE, not just the model's self-consistency. The
    # earlier form compared retry to verify in code and never read the prose, so
    # reversing "retry buys more than verify" left it green.
    check(f"retry beats verify at {steps} steps for about half the calls",
          retry_p > verify_p and 0.45 <= retry_c / verify_c <= 0.55,
          f"{retry_p:.3f} vs {verify_p:.3f} at "
          f"{retry_c:.1f} vs {verify_c:.1f} calls")
    check(f"README says so, in that direction (At {steps} steps, retry buys "
          f"more reliability than verify for half the calls)",
          re.search(rf"At {steps} steps, retry buys more reliability\s+"
                    rf"than verify for half the calls", readme) is not None,
          "the sentence at README ~line 83 must match the model's direction")

    print("results table, re-aggregated from the committed runs/*.jsonl:")
    aggs = {}
    for label, filename in TABLE:
        run_path = REPO / "runs" / filename
        check(f"{label}: {filename} is committed", run_path.exists())
        if not run_path.exists():
            continue
        agg = aggregate(load_run(run_path))
        aggs[label] = agg
        row = table_row(readme, label)
        check(f"{label}: the README table has this row", bool(row))
        ok, scored = per_step_counts(agg)
        check(f"{label}: README quotes per-step {ok}/{scored}",
              f"{ok}/{scored}" in row, row.strip())
        # A clean sweep carries no percentage; anything else must. Deriving that
        # expectation from the counts rather than sniffing the row for a
        # percentage matters: the old form gated the check on the number being
        # there, so deleting the number deleted the check instead of failing it.
        if ok == scored:
            check(f"{label}: a clean sweep needs no percentage",
                  not re.search(r"\(\d+\.\d+%\)", row), row.strip())
        else:
            check(f"{label}: README quotes per-step {ok / scored:.1%}",
                  f"({ok / scored:.1%})" in row, row.strip())
        e2e = f"**{agg['observed_e2e']:.0%}**"
        check(f"{label}: README quotes end-to-end {e2e.strip('*')}",
              e2e in row, row.strip())
        # One number for one run: the report committed beside the log has to
        # divide by the same thing the log does.
        md = run_path.with_suffix(".md")
        check(f"{label}: the committed report agrees on end-to-end",
              md.exists() and
              f"**Observed end-to-end success: {agg['observed_e2e']:.0%}**"
              in md.read_text(encoding="utf-8"))

    print("the failures the README narrates, read back out of the logs:")
    clean = only_failure(load_run(REPO / "runs" / "qwen3.6-27b_none.jsonl"))
    check("the clean run has exactly one failing step", len(clean) == 1,
          f"{len(clean)} failing steps")
    if len(clean) == 1:
        got, expected = two_numbers(clean[0]["detail"])
        check(f"README names the failing step (`{clean[0]['step']}`)",
              f"`{clean[0]['step']}`" in readme, clean[0]["detail"])
        check(f"README quotes the slip as {got} instead of {expected}",
              f"{got} instead of {expected}" in readme, clean[0]["detail"])
        check(f"README sizes the slip at ${abs(expected - got):.0f}",
              f"${abs(expected - got):.0f} arithmetic slip" in readme,
              clean[0]["detail"])
        # Scope this to the table row that describes THIS failure. Whole-README
        # containment passed for any class name, because the taxonomy section
        # lists all five in backticks, so flipping the run's outcome to
        # format_error still printed "ok".
        row = next((ln for ln in readme.splitlines()
                    if "| clean documents |" in ln), "")
        check(f"the clean-documents row names its class "
              f"(`{clean[0]['outcome']}`)",
              f"`{clean[0]['outcome']}`" in row,
              f"row says: {row.strip()[:120] or 'row not found'}")

    verify_records = load_run(REPO / "runs" / "qwen3.6-27b_verify.jsonl")
    missed = only_failure(verify_records)
    check("the verify run has exactly one failing step", len(missed) == 1,
          f"{len(missed)} failing steps")
    if len(missed) == 1:
        got, expected = two_numbers(missed[0]["detail"])
        cents = round(abs(expected - got) * 100)
        check(f"README calls the verifier's miss a {cents}-cent conversion "
              f"error", f"{cents}-cent conversion error" in readme,
              missed[0]["detail"])
        check(f"README's closing line spells that miss as {ONES[cents]} cents",
              cents < len(ONES) and f"{ONES[cents]} cents" in readme,
              missed[0]["detail"])
    verify_agg = aggs.get("clean + `verify`") or aggregate(verify_records)
    flags = f"{verify_agg['verifier_flags']} of {verify_agg['verifier_checks']}"
    check(f"README quotes the verifier flagging {flags} steps",
          f"{flags} steps" in readme, flags)

    print("the reproduction surface the README shows verbatim:")
    client = OllamaClient()
    check(f"README quotes the model tag ({client.model})",
          client.model in readme)
    check(f"README quotes the sampling temperature (temp {client.temperature})",
          f"temp {client.temperature}" in readme)
    label = client.model.replace(":", "-").replace("/", "-")
    check(f"the committed runs are that model's ({label}_*.jsonl)",
          all((REPO / "runs" / f).name.startswith(label + "_")
              for _, f in TABLE))
    check(f"README calls the agent {len(STEPS)}-step",
          f"{len(STEPS)}-step" in readme)
    if "clean documents" in aggs:
        shape = f"{aggs['clean documents']['n_docs']} docs × {len(STEPS)} steps"
        check(f"README's results heading quotes {shape}", shape in readme)

    spec = importlib.util.spec_from_file_location(
        "_readme_claims_tests", REPO / "tests" / "test_realmode.py")
    suite = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(suite)  # defines the tests; runs none of them
    n_tests = len([k for k in vars(suite) if k.startswith("test_")])
    check(f"README says the suite runs {n_tests} tests",
          f"runs {n_tests} tests" in readme,
          f"tests/test_realmode.py defines {n_tests}")

    rng = random.Random(SEED)
    truth = make_ground_truth(1, rng)
    document = render_document(truth, rng)
    check(f"README shows the real document 1 at seed {SEED}",
          document in readme)
    check(f"README quotes its trip line ({len(truth.items)} claimable items)",
          f"trip: {truth.start} to {truth.end} · {len(truth.items)} "
          f"claimable items" in readme)
    check(f"README quotes its grand total ({truth.grand_total} USD)",
          f"grand total: {truth.grand_total} USD" in readme)
    item_lines = [f"{i.description}: {i.amount} {i.currency} = "
                  f"{i.amount_usd} USD ({i.category})" for i in truth.items]
    quoted = [line for line in item_lines if line in readme]
    check("README's excerpted ground-truth item line matches generation",
          len(quoted) == 1, f"{len(quoted)} of {len(item_lines)} lines matched")

    if problems:
        print(f"\n{len(problems)} README claim(s) drifted: {problems}")
        return 1
    print("\nevery quoted README number matches its artifact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
