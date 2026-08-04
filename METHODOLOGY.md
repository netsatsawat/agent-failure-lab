# Test methodology

How the real-mode experiments are designed, graded, and bounded. Written so
a practitioner can reproduce them, audit them, or disagree with them
precisely.

## Research questions

1. **Compounding.** Does measured per-step accuracy compound into end-to-end
   failure the way the analytic model (`p_eff^n`) predicts?
2. **Taxonomy.** How do a real model's failures distribute across
   code-detectable classes (format, tool) versus value errors
   (hallucination, arithmetic)?
3. **Mitigation economics.** What do `retry` and `verify` buy in end-to-end
   success, and at what cost in LLM calls?
4. **Adversity.** Does document-level adversity (noise, decoys, bait) change
   the failure profile, or just the difficulty?

## System under test

An 8-step document-processing agent: extract dates, extract items,
categorize, request exchange rates (a tool call), convert amounts, sum by
category, policy check, final summary. Each step is one LLM completion with a
strict JSON instruction, and each step consumes the agent's own prior
outputs, so errors propagate as they would in production.

Model configuration for the shipped runs: `qwen3.6:27b` (Q4_K_M) via Ollama,
temperature 0.2, `num_predict` 700, thinking disabled. Constrained decoding
(`format: json`) is deliberately off. The lab measures the model's natural
format-error rate, and grammar-constrained sampling would sanitize away one
of the failure classes under study.

## Test data

Documents are synthetic and seeded. Each is rendered from a structured ground
truth (employee, trip dates, 5 to 7 line items with amounts in THB/EUR/USD
and true categories), so the correct output of every step is computable. The
same `--seed` reproduces the same documents byte for byte, and
`realmode.py show-doc` prints any of them. Synthetic data trades realism for
three properties that matter more here: exact ground truth, zero chance of
training-set contamination for these specific documents, and deterministic
reproduction.

Rendering varies date formats, currency symbols, and separators. The
`--hard` flag adds scan-noise lines, shuffled item order, a
`[VOIDED - do not reimburse]` line that must be excluded, and a printed
"Total claimed" that is deliberately wrong. None of it changes the ground
truth.

## Variables

- **Independent:** mitigation (`none`, `retry`, `verify`), document adversity
  (clean, `--hard`), model tag (`--model`).
- **Controlled:** seed (42), temperature (0.2), prompts, document count (8),
  step definitions, tolerances.
- **Dependent:** per-step outcome (success, `wrong_value`, `format_error`,
  `tool_error`, `infra_error`), attempts per step, end-to-end success,
  verifier checks and flags, per-step latency, expected LLM calls.

## Grading protocol

**Layer 1: per step, against conditional truth.** Each step is scored against
the correct answer given the agent's actual inputs, meaning its own prior
outputs. A step is never blamed for inherited errors, so the taxonomy
isolates each step's skill. Classification precedence: parse and shape
failures are `format_error`; invalid or mis-targeted tool calls are
`tool_error`; well-formed output with wrong content is `wrong_value`.
Transport failures are `infra_error` and are excluded from model-quality
denominators.

**Layer 2: end to end, against absolute truth.** The final summary must match
the document's true employee, dates, grand total, and policy flags. This is
the compounding metric. A document counts as an end-to-end failure if any
step ended in a code-detectable failure (the chain visibly broke there, and
the oracle is substituted so downstream steps stay measurable) or if the
final summary misses absolute truth.

**Numeric tolerances.** Per-item conversions: 0.011 (rounding slack, one cent
plus float noise). Category totals: 0.02. Conditional grand totals: 0.05.
The end-to-end grand-total tolerance is the worst-case accumulation of the
per-step tolerances (0.011 × items + 0.05), so per-step rounding alone can
never produce a run where every step is green yet end-to-end fails. Every
unexplained end-to-end failure traces to a classified step failure.

**Consistency rules.** Duplicate item descriptions are classified as that
step's `wrong_value` and deduplicated before flowing downstream, so one
mistake is charged once. Items whose descriptions match neither ground truth
nor the template table have no defined true category, and any valid category
is accepted for them. A step is never charged twice for an upstream
rewording.

## Mitigation implementations

- **`retry`** models the case where failure detection is free (schema
  validation, tool errors). One retry on code-detectable failures only.
  `wrong_value` is invisible to it by construction.
- **`verify`** adds a second LLM call that reviews each step's raw output
  against the task prompt and verdicts pass or fail. The verifier is blind:
  it never sees ground truth. A fail verdict buys one corrected attempt,
  which is not re-verified. Checks and flags are logged per step, and runs
  record attempt-level outcomes (`attempt_outcomes`), which is what
  separating verifier precision (false flags on correct work) from recall
  requires.

## Harness validation

The measuring instrument is itself under test. A deterministic oracle mock
replays the full pipeline with known-perfect answers, and with injected
garbage, wrong tool calls, wrong values, and transient failures. The suite
asserts that a perfect agent scores 100% end to end (the literal-reading
fairness test: doing exactly what the prompts say must be sufficient), that
each injection lands in its intended class, that `retry` recovers transient
code-detectable failures and never fires on `wrong_value`, that the verifier
flow buys exactly one corrected attempt, that decoy descriptions cannot
collide with real items, and that duplicates are caught.
`python tests/test_realmode.py` runs all of it with no model.

## Threats to validity

- **Sample size.** 8 documents × 8 steps per condition demonstrates that the
  pipeline and the math connect. It is not a benchmark, and end-to-end rates
  are k/8 with wide intervals.
- **Single model, single temperature.** These results are one point in a
  large space. Smaller models and higher temperatures should shift the
  taxonomy toward format errors.
- **Synthetic documents.** Even hard mode is cleaner than real scanned
  paperwork, so absolute success rates are optimistic. What transfers is the
  compounding structure, not the levels.
- **Verifier precision unresolved.** In the shipped verify run, flagged then
  corrected steps ended correct, and whether their first attempts were
  actually wrong is not separable in that log. Attempt-level outcome logging
  exists for exactly this analysis in future runs.
- **Non-independence.** Per-step rates within a run share documents, and the
  predicted end-to-end figure assumes independence across steps.
- **Environment sensitivity.** Latency figures vary with machine load. They
  are reported descriptively, never as model quality.

## Reproducing

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python tests/test_realmode.py                    # harness validation, no model
ollama pull qwen3.6:27b                          # or any tag via --model
python realmode.py run --docs 8 --mitigation none
python realmode.py run --docs 8 --mitigation verify
python realmode.py run --docs 8 --hard
```

Same seed, same documents. Reports and taxonomy charts are written next to
each run's JSONL in `runs/`.
