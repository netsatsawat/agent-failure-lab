<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/banner-dark.png">
    <img src="assets/banner-light.png" alt="agent-failure-lab" width="100%">
  </picture>
</h1>

<p align="center">
  <a href="#-feel-the-math-no-model-needed">Feel the math</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="#-prove-it-on-a-real-model">Prove it on a real model</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://netsatsawat.github.io/agent-failure-lab/">Live calculator</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://www.amazon.com/dp/B0H17XQ9SY">The book</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.9+"></a>
  <img src="https://img.shields.io/badge/API%20keys-none-1baf7a?style=for-the-badge" alt="No API keys">
  <img src="https://img.shields.io/badge/real%20mode-local%20Ollama-eb6834?style=for-the-badge" alt="Real mode: local Ollama">
  <a href="https://netsatsawat.github.io/agent-failure-lab/"><img src="https://img.shields.io/badge/live-calculator-2a78d6?style=for-the-badge" alt="Live calculator"></a>
  <a href="https://satsawat.ai"><img src="https://img.shields.io/badge/author-satsawat.ai-e8a112?style=for-the-badge" alt="Author: satsawat.ai"></a>
</p>

> Each step of an AI agent makes small mistakes. Those mistakes multiply into one big failure. Watch it happen with a formula, then watch two fixes, retry and verify, pull that failure rate back down.

Chain 10 steps at 85% per-step accuracy and your end-to-end success rate is
**19.7%**. Every AI leader nods at that sentence. Almost nobody feels it. The
number is nothing fancy, just 0.85 multiplied by itself ten times. You can run
that arithmetic here with one command. Arithmetic alone never convinced a
skeptic, so the lab also runs a real agent on your own computer. An AI agent
here is a program that does a job by sending a language model one request per
step. This one runs 8 steps to process expense reports. Every step the agent
takes is checked against the known right answer and written to a log, so you
can watch the same multiplying failure happen for real.

This repo is for engineers and technical leads who build or approve
multi-step agents. Anyone who can follow basic Python can read it.

Companion code for the book [*Why Your AI Agent Will
Fail*](https://www.amazon.com/dp/B0H17XQ9SY) and the writing at
[satsawat.ai](https://satsawat.ai).

![python simulate.py, the compound-failure table](assets/simulate.gif)

## 🧭 Why this repo exists

An AI agent, in this repo, is a program that finishes a job by sending a
language model a series of requests, one per step: extract, look up,
transform, decide, summarize. One request and its reply is one model call.
Each call is right most of the time. The final answer is only right when
every step is right, so the per-step error rates multiply against you. At 85%
per step, a 3-step demo works about 3 times in 5 (61%), which is enough to get
a project approved. Now keep the same 85% per step and stretch the chain to
10 steps. It works 1 time in 5 (20%). Worse, most of those failures are
confidently wrong answers rather than crashes, so your logs stay green while
your users lose trust.

Waiting for a better model does not fix this. How you build the chain of
steps around the model does. There are two standard fixes, retry and verify.
They cost very different amounts. One question decides which one to use:
can ordinary code tell that the step failed? A reply that is not in the shape
the code asked for, or a request to a helper function with the wrong inputs,
is free to catch and cheap to retry. A wrong number inside a well-formed
reply is different. Catching it needs a second model call, and that second
call misses things.

### The words you need

Seven terms, one name each. Where the code uses a second name, the line says
so.

- Model: the AI language model that answers each step. LLM, short for large
  language model, is the same thing, and the code and its output say LLM.
- Per-step accuracy: how often one step gives the right answer, written as a
  fraction like 0.85. `simulate.py` takes it as `--accuracy`. The 85% used
  throughout this file is a chosen example value, the `--accuracy` default,
  not a measurement.
- End-to-end success: the whole chain got the final answer right. With no fix
  it is per-step accuracy raised to the power of the number of steps, so 0.85
  to the power 10 is 0.197.
- Fix: something you add around the model to recover from a failed step. The
  code calls a fix a mitigation, which is why the flag is `--mitigation`.
  There are two fixes.
  - Retry: when code can tell a step failed, run that step once more. It costs
    one extra call, and only when a step fails.
  - Verify: after every step, ask the model a second time whether the step's
    output looks right. That second call is the verifier. If the verifier says
    no, the step gets one corrected attempt. Each step costs 2 calls (the step
    plus the check), and 3 when the verifier says no.
- Verifier recall: the share of truly wrong steps the verifier catches. The
  math assumes 90%, so the verifier catches 9 of every 10 real mistakes. The
  90% is a chosen setting, not a measurement. It lives in
  `failure_lab/model.py` as `DEFAULT_VERIFIER_RECALL`, and the slider app
  below lets you change it.
- Code-detectable failure versus `wrong_value`: a code-detectable failure is a
  reply that is not in the shape the code asked for (`format_error`), or a
  request to a helper function with the wrong inputs (`tool_error`). A tool
  here is a plain function the agent can ask to run, like a currency-rate
  lookup. A `wrong_value` is a well-formed reply with wrong content, such as a
  wrong date or a wrong sum. The run's reports call a `wrong_value` a
  hallucination. Retry can only see the code-detectable kind.
- Ground truth: the known correct answer. The lab writes the correct answers
  first and then builds each expense report from them, so the code always
  knows what every step should produce.

This lab lets you hold the whole argument in your hands. Run the formula, drag
sliders on it, then run the real agent and watch where its failures land: what
the verifier catches, what it costs, and what it misses.

Real mode, the part of the lab that runs the agent on a real model, also
needs Ollama, a free program that runs open language models on your own
computer. No API key is involved anywhere in this repo. An API key is the
access token a cloud model service bills you through, and nothing here calls
a cloud service.

## 🧮 Feel the math (no model needed)

The simulator needs Python 3.9 or newer and nothing else. Download the repo
with git and run one command. On macOS the command may be `python3` rather
than `python`.

```
git clone https://github.com/netsatsawat/agent-failure-lab.git
cd agent-failure-lab
python simulate.py
```

You will see this table:

```
Per-step accuracy: 85%   trials per cell: 20000
verify = 90%-recall LLM verifier + one corrected attempt · retry = one retry on code-detectable failures

steps |       none       |      verify      |      retry      
--------------------------------------------------------------
    1 |   85.0% (85.1%)  |   96.5% (96.6%)  |   97.8% (97.7%) 
    2 |   72.2% (72.2%)  |   93.1% (93.2%)  |   95.6% (95.6%) 
    3 |   61.4% (61.0%)  |   89.8% (89.8%)  |   93.4% (93.2%) 
    4 |   52.2% (51.7%)  |   86.6% (86.3%)  |   91.3% (91.7%) 
    5 |   44.4% (45.0%)  |   83.6% (83.6%)  |   89.2% (89.3%) 
    6 |   37.7% (37.7%)  |   80.6% (81.2%)  |   87.2% (86.8%) 
    7 |   32.1% (32.2%)  |   77.8% (77.3%)  |   85.3% (85.4%) 
    8 |   27.2% (26.9%)  |   75.0% (75.7%)  |   83.4% (83.4%) 
    9 |   23.2% (22.9%)  |   72.4% (72.4%)  |   81.5% (82.0%) 
   10 |   19.7% (19.4%)  |   69.8% (70.1%)  |   79.6% (79.9%) 

format: analytic (simulated)
expected LLM calls for the 10-step chain: none 10.0 · verify 21.4 · retry 11.5
```

Each row is a chain length. Across the top are the three fixes: `none`,
`verify` or `retry`. In each cell, the first number comes from the formula.
The number in brackets comes from 20,000 simulated chains driven by random
coin flips, a Monte Carlo run, and it is there to show the formula is right.
The line `format: analytic (simulated)` names the two: analytic is the
formula, simulated is the bracketed number. Those coin flips are seeded with
42. A seed is the starting number for the random generator, so the same seed
gives the same flips and the same output every time. Row 3 in the `none`
column is the demo that passes: 61.4%, about three times out of five. Row 10
is the same agent in production, at 19.7%. The banner line says "90%-recall
LLM verifier", which means the verifier catches 9 of every 10 real mistakes.

The last line is the cost of the 10-step chain in model calls, because calls
are the unit this lab uses for cost. `none` is 10 calls, one per step.
`retry` is 11.5: 10 first attempts plus 1.5 retries on average, since 15% of
steps fail and each failed step gets one more call. `verify` is 21.4: 10
first attempts, 10 verifier calls, and about 1.4 corrected attempts (the 15%
of steps that fail, times the 90% the verifier catches, times 10 steps).
At 10 steps, retry buys more reliability than verify for half the calls:
79.6% for 11.5 calls against 69.8% for 21.4 calls. The catch is that retry
only works on failures code can detect. Real agents need both: retry on steps
whose failures code can spot (bad format, wrong tool call), verify on steps
that produce numbers or judgments.

Two generous assumptions sit inside the `verify` column. The verifier never
flags correct work, and a corrected attempt succeeds as often as a first try,
85%. Real mode logs every verifier decision and, in new runs, the outcome of
every attempt, so future runs can measure how far a real model sits from both
assumptions. The three shipped logs were written before per-attempt outcomes
were recorded, so they cannot show whether the verifier ever flagged correct
work, which is the first of those two assumptions.

![The two fixes at 85% per-step accuracy](assets/mitigations.png)

Two more commands run with no model.

`python tests/test_realmode.py` runs 12 tests against the grading code. The
tests use the oracle mock, a fake model that answers every step from ground
truth and can be told to inject specific failures. The command prints one
PASS line per test and then `12 tests passed`.

`python realmode.py run --mock --docs 3` runs the full expense-report agent
on three documents with the same fake model. It needs
`pip install -r requirements.txt`, for the chart only. Without that install
the agent run completes, then the report step stops with an ImportError and
only the `.jsonl` file is written, a plain text log with one record per line.
With the install in place, the command writes three files under `runs/`:
`mock_none.jsonl`, `mock_none.md` and `mock_none.png`. They are output, not
source, so do not add them to git.

### Other ways to see the math

Three other ways to see the same numbers: a Jupyter notebook, a slider app,
and a web page with no install. The notebook and the slider app import
`failure_lab/model.py` directly. The web calculator redoes the arithmetic in
JavaScript so it can run as one file.

Start with the notebook if you want the full walkthrough: the arithmetic, the
Monte Carlo agreement, the curve for each fix, the cost of reliability and
the reliability-budget table. That table answers the reverse question: what
per-step accuracy do you need for a given end-to-end target? To promise 90%
over 10 steps with no fix, each step must hit the 10th root of 0.90, which is
0.9895, so 98.95% per step. The notebook has its outputs embedded, so it
renders complete on GitHub.

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter notebook notebook/compound_failure_walkthrough.ipynb
```

The slider app is built with Streamlit, a Python library that turns a script
into a web page. It puts sliders on the same model: `streamlit run app.py`.

The web calculator is one file, [`docs/index.html`](docs/index.html), with no
dependencies. It is live at https://netsatsawat.github.io/agent-failure-lab/
and you can serve your own copy through GitHub Pages, GitHub's built-in way
to publish a folder as a website (Settings, then Pages, deploy from `/docs`).
Light and dark mode, hover tooltips.

## 🔬 Prove it on a real model

Real mode runs an 8-step expense-report agent against a model on your own
machine and grades every step. The shipped runs used one model,
`qwen3.6:27b`, at one sampling temperature, `temp 0.2`. The 27b in the name
is the model's size, in billions of parameters. Size decides how much memory
the model needs. Sampling is how the model picks each next word. The
temperature setting is how much randomness that pick gets. A lower
temperature means the model picks its most likely words more often, so
answers vary less between runs.

Each run is only 8 documents, so one document passing or failing moves the
end-to-end rate by 12.5 percentage points. Read the table with that in mind.
Per-step success counts steps that ended correct, whatever it took to get
there. A step the verifier sent back and then passed counts as a success with
two attempts.

### Results (qwen3.6:27b, temp 0.2, 8 docs × 8 steps)

| run | per-step success | end-to-end | what happened |
|---|---|---|---|
| clean documents | 63/64 (98.4%) | **88%** | one wrong step: `sum_categories` summed to 669.03 instead of 670.03. A $1 arithmetic slip, class `wrong_value`, invisible to retry |
| hard documents | 64/64 | **100%** | every step passed, through the noise line, the VOIDED decoy and the wrong printed total |
| clean + `verify` | 63/64 (98.4%) | **88%** | the verifier sent 9 steps back for a second try (all then passed) and waved through the one step that was wrong, a 6-cent conversion error. Same 88%, about twice the calls |

At only 8 documents, hard mode scoring higher than clean is luck, not a sign
that hard mode is easier.

Clean documents, no fix. 64 step attempts, one wrong, so per-step success is
63/64. That one wrong step sank its document, so 7 of 8 documents passed, the
88% in the table. Document 8 was the casualty: on its `sum_categories` step
the model added the category totals and came out at 669.03 instead of 670.03.
Its reply was valid JSON with the right keys. JSON is the text format every
step must reply in, named fields with values, such as
`{"grand_total": 670.03}`. No code check could have noticed a wrong number in
a well-formed reply, so retry would never have fired. You can find the log
entry in `runs/qwen3.6-27b_none.jsonl` with the detail
`grand_total 669.03 vs 670.03`.

Hard documents, no fix. All 64 steps passed, so all 8 documents passed. A
clean sweep at this size says little. At the clean run's measured 98.4% per
step, the chance that all 64 steps pass is 0.984 to the power 64, about 36%.
A perfect run is unremarkable, and it does not mean hard mode is easier.

Clean documents with `verify`. The verifier looked at all 64 steps and
flagged 9 of 64 steps, sending each one back for a second attempt: three
`convert_amounts` steps, four `sum_categories` steps, one `extract_items`
step and one `policy_check` step. All nine second attempts passed. One of the
nine was document 8's `sum_categories`, the same document and step that
failed in the no-fix run. Whether any of those nine first attempts was wrong
is not in this log, so I cannot say how often the verifier complained about
work that was fine (its false-flag rate). The verifier also looked at
document 6's `convert_amounts` step and passed it, and that step was wrong:
the hotel line came out as 153.1 instead of 153.16, a 6-cent conversion
error. End-to-end stayed at 7 of 8 while the cost roughly doubled: the no-fix
run made 64 calls and this run made 137. The 137 is 64 first attempts, plus
64 verifier calls, plus 9 corrected attempts. The two counts behind that sum
are in `runs/qwen3.6-27b_verify.md`, printed as "64 checks, 9 flags raised"
and "steps retried: 9".

In every run the observed end-to-end matched the prediction the report makes
from the measured per-step rates. The report multiplies the eight per-step
rates together. In the clean run seven steps scored 8/8 and `sum_categories`
scored 7/8, so the product is 7/8, or 88%, and 88% is what the run produced.
At 8 documents that match shows the real agent and the formula agree. It is too
small to be a ranking of models. An LLM verifier earns its cost only if it
catches the small errors, and the error this one missed was six cents. Full
logs, reports and charts are in `runs/`.

### What the agent does

The 8 steps, in order. Each one is a single model call that must reply in
JSON. Steps 1 and 2 read only the document. Steps 3 to 8 also read the
agent's own earlier outputs.

1. `extract_dates`: read the trip start and end dates.
2. `extract_items`: list the expense lines with amount and currency.
3. `categorize`: label each item as meals, lodging, transport, supplies or
   other.
4. `request_rates`: write a request to the `exchange_rate` tool for each
   non-USD currency present. Step 4 only writes the tool request. No tool
   actually runs. The request itself is graded, and step 5 is handed the full
   fixed rate table whatever step 4 asked for. So step 4 measures tool
   calling and step 5 measures arithmetic.
5. `convert_amounts`: turn every amount into USD with the rates.
6. `sum_categories`: add up each category and the grand total.
7. `policy_check`: answer three yes/no questions (total over 2000, any single
   item over 500, trip longer than 7 days).
8. `final_summary`: write the final record with employee, dates, grand total
   and flags.

Every step attempt ends in one of five outcomes:

- `success`: matches the correct answer within a rounding allowance, about
  one cent per item, two cents per category total and five cents on a grand
  total. [METHODOLOGY.md](METHODOLOGY.md) has the exact figures.
- `format_error`: the reply was not the JSON shape the step asked for. Code
  can detect it.
- `tool_error`: the wrong tool, or the wrong currencies asked of the rate
  tool. Code can detect it.
- `wrong_value`: well-formed but wrong. Only a verifier or ground truth
  catches it.
- `infra_error`: the request to the model failed, for example a dropped
  connection or a timeout. It is a transport or runtime failure, not a model
  mistake. It is counted separately, and the whole document is dropped from
  the scores, so a network blip never looks like a model mistake.

In real mode, verify does everything retry does (one free second try on a
`format_error` or `tool_error`) and also runs the verifier on every reply
that came back in the right shape. The corrected attempt is not checked
again. The verifier is blind: it sees the task prompt and the step's raw
output, never the ground truth.

### The documents, and how grading works

Documents are generated, not collected, and that is what makes automatic
grading possible. `python realmode.py show-doc` prints document 1 at the
default seed of 42, and `--seed` changes it:

```
EXPENSE REIMBURSEMENT REQUEST
Submitted by: Farid Rahman
Trip period: January 01, 2026 to January 07, 2026

Expenses claimed:
  - Whiteboard markers and notepads .... €81.16
  - Team dinner at riverside restaurant .... EUR 77.91
  - Taxi from airport .... THB 640.00
  - Baggage fee for equipment .... €23.89
  - Hotel room - 2 nights .... EUR 304.46

Please process according to company travel policy.
Reference: TRIP-0001

--- ground truth (what the agent is graded against) ---
trip: 2026-01-01 to 2026-01-07 · 5 claimable items
  Taxi from airport: 640.0 THB = 17.92 USD (transport)   ...
grand total: 544.33 USD · flags: none
```

The lines under "ground truth" are the known answers. The taxi line is one of
five (the other four are cut here): 640 THB at the fixed rate of 0.028 in
`failure_lab/realmode/documents.py` is 17.92 USD. Same seed, same documents,
every time. Rendering varies the date formats and currency symbols and mixes
THB, EUR and USD amounts. The `--hard` flag makes the documents messier: one
junk scan line, shuffled items, one line marked `[VOIDED - do not reimburse]`
that the agent must skip, and a printed "Total claimed" that is deliberately
wrong, as bait for any agent that copies instead of computing. None of it
changes the ground truth.

Grading happens at three layers. The full design, with the numeric
tolerances, is in [METHODOLOGY.md](METHODOLOGY.md).

1. Per step, against conditional truth. Each step is judged against the
   correct answer given the agent's own earlier outputs, even when those were
   wrong. A step is never blamed for an error it inherited, so the outcome
   counts measure each step's own skill. Wrong values still flow downstream,
   exactly as in production.
2. End to end, against absolute truth. The final summary must match the
   document's real employee, dates, grand total and policy flags. End-to-end
   success is the number that compounds.
3. The grading code itself is tested. `python tests/test_realmode.py`
   runs 12 tests with the oracle mock. They check that:
   - a perfect agent scores 100%,
   - each injected failure (garbage output, wrong tool, wrong value, and a
     transport error, the `infra_error` class above) lands in its intended
     class,
   - retry recovers a one-off format error and never fires on a
     `wrong_value`,
   - verify buys exactly one corrected attempt,
   - duplicate items are caught as a `wrong_value`,
   - a document whose chain hit a transport error is excluded from the
     per-step rates as well as the end-to-end one.

   Two fairness guarantees live in the code but have no test yet: the VOIDED
   decoy is chosen so it can never share a description with a real item, and
   an item that is not in the ground truth, such as that decoy, still gets
   its true category from the table the documents are generated from.

### Reproduce it from scratch

1. Python side, any machine: `python -m venv .venv && source
   .venv/bin/activate && pip install -r requirements.txt`. The environment is
   for the charts, the reports, the notebook and the app. The simulator and
   the tests need neither the environment nor a model.
2. Install [Ollama](https://ollama.com/download). macOS and Windows have
   installers. On Linux: `curl -fsSL https://ollama.com/install.sh | sh`. Then
   pull the model the shipped results used: `ollama pull qwen3.6:27b`. It is a
   large download, and the machine needs enough memory to hold a model this
   size. This repo does not record the exact download size, so check the
   model's page in the [Ollama library](https://ollama.com/library) before you
   pull. Other tags (a tag is Ollama's name for one model
   version) from that same library can be passed through `--model`, though only
   `qwen3.6:27b` has been run here.
   Smaller models run on modest hardware and fail more often, and watching
   them fail is what the lab is for. Confirm the server is up with
   `ollama list`. Ollama listens at `localhost:11434`, an address on your own
   machine, and the code talks to it there.
3. Run the experiments. `--model` defaults to `qwen3.6:27b` and `--seed` to
   42, so the last three commands use the same model and the same documents
   as the first:

```
python realmode.py run --docs 8 --model qwen3.6:27b        # no fix
python realmode.py run --docs 8 --mitigation retry         # free retry on code-detectable failures
python realmode.py run --docs 8 --mitigation verify        # blind LLM verifier per step
python realmode.py run --docs 8 --hard                     # messier documents
```

4. Read the results. Each run streams `runs/<model>_<mitigation>[_hard].jsonl`,
   a file with one JSON record per line: one record per step, carrying its
   attempt count, plus one end-to-end record per document. The run also
   writes a markdown report and a per-step outcome chart beside the log.
   Rebuild any report with `python realmode.py report runs/<file>.jsonl`.
   Inspect any document with
   `python realmode.py show-doc [--doc-id N] [--seed 42] [--hard]`.

No `retry` run is committed. In the no-fix run no step ended in a
`format_error` or `tool_error` (both columns read 0% in
`runs/qwen3.6-27b_none.md`), so retry would have had nothing to fire on.

### Limits

- 8 documents per condition. Every rate here is a count out of 8, so the
  true rate could sit well above or below the one shown.
- One model at one temperature. My expectation is that smaller models and
  higher temperatures shift the outcomes toward `format_error`. I have not
  measured that.
- Synthetic documents. Even hard mode is cleaner than real scanned paperwork,
  so the success levels are optimistic. The compounding structure transfers
  to real paperwork. The success levels do not.
- The verifier's false-flag rate cannot be read from the shipped logs. New
  runs record the outcome of every attempt in an `attempt_outcomes` field for
  that analysis. The three committed logs predate the field.
- The predicted end-to-end figure assumes each step fails on its own,
  unaffected by the others. Steps within a run share documents, so that may
  not hold.

## 🗂 Repo layout

```
METHODOLOGY.md             experimental design, grading protocol, threats to validity
failure_lab/model.py       the formula and the Monte Carlo simulation (single source of truth)
failure_lab/charts.py      shared chart code (notebook, app, README charts)
failure_lab/realmode/      real mode: documents, agent steps, model clients, report
simulate.py                the simulator command, standard library only
realmode.py                the real-mode command (Ollama or oracle mock)
tests/test_realmode.py     real-mode tests, same result every run (no model needed)
notebook/                  executed walkthrough (charts embedded, renders on GitHub)
app.py                     the Streamlit slider app
docs/index.html            standalone web calculator (GitHub Pages ready)
runs/                      real-mode results: a JSONL log, markdown report and outcome chart per run
scripts/                   generators: charts, notebook, README GIF, README claim checker
```

`scripts/verify_readme_claims.py` runs on every change pushed to the repo,
as part of CI, the automatic check GitHub runs on each push. It recomputes
the 19.7% headline from `failure_lab/model.py`, re-aggregates the three
committed logs in `runs/`, and blocks the change if a checked number in this
file no longer matches. It checks a fixed list: the headline, every row of
the results table, the two failures described by hand, the sample document,
the model settings and the test count. The other numbers in this file are
arithmetic you can redo from those, such as 137 calls from 64 + 64 + 9.

## 🔭 What's next

Each item below is an open question the current results raise but cannot
answer at 8 documents. In rough priority order:

- More documents. Run 50 to 100 documents per condition so the end-to-end
  rates carry real confidence intervals, a range the true rate is likely to
  sit in. The report predicts end-to-end as `p_eff^n`, the per-step rate
  after a fix raised to the number of steps. Will real end-to-end rates keep
  matching that, or fall below it? Falling below would mean failures
  correlate: documents that trip one step tend to trip others. My
  expectation from production incidents is that they do. This lab can
  measure it.
- Cross-model runs. Same seed, same documents, different `--model` tags. The
  lab's own thesis predicts smaller models shift the outcomes toward
  `format_error` while big models fail quietly as `wrong_value`. If that
  holds, it has a practical consequence: small-model failures are the cheap,
  code-detectable kind, so a small model plus `retry` may beat a large bare
  model on cost per successful chain. That claim is testable here in an
  afternoon.
- Verifier precision and recall by error size. Precision is the share of
  flags that landed on a step that was really wrong, and recall is the share
  of really wrong steps that got flagged. New runs log the outcome of every
  attempt, so the verifier's false-flag rate becomes measurable directly. The
  complement is a recall sweep: inject `wrong_value` corruptions of
  controlled size (one cent, one dollar, ten percent) and chart the catch
  rate against error size.
  The shipped run's 6-cent miss suggests recall falls off exactly where you
  need it most. A related variant worth testing is a different model as the
  verifier, since self-checking may share the worker's blind spots.
- More fixes from real deployments. Three candidates, in order of interest.
  Constrained decoding: turn Ollama's `format: json` option on, which forces
  the model to emit valid JSON, and measure how much of the format class it
  removes and whether forcing valid JSON hurts value accuracy. Step fusion:
  merge the 8 steps into 4, trading per-call complexity against chain length,
  which is the architecture lever the book argues for. Majority vote on the
  arithmetic steps, where the observed failures live: ask the same step
  several times and keep the answer most replies agree on.
- `agent-report-card` integration. `agent-report-card` is a separate tool
  for grading agent runs. Each run here already writes a log with every
  step, its outcome, its attempt count and the verifier's verdicts. The goal
  is to freeze that log format so the separate tool can grade it and compare
  two versions of an agent, and stop a release when the new version does
  worse.
- Real-document mode. The honest gap in this lab is that even hard mode is
  cleaner than production paperwork. Synthetic documents are what make exact
  grading possible, so bring-your-own-documents needs a labeling story first.
  The likely shape is a helper that drafts ground truth for your documents and
  has you confirm it once, after which the same grading protocol applies.

Runs on other models with the same seed are especially welcome as issues or
PRs, a PR being a pull request, the way GitHub takes a proposed change to the
code. Cross-model comparison is where a single machine runs out of road.

---

Written by [Satsawat Natakarnkitkul](https://satsawat.ai), a data & AI leader
in ASEAN and the author of *Why Your AI Agent Will Fail*. Newsletter:
[AI in Practice](https://satsawat.ai/#newsletter)

License: MIT
