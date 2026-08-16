"""The 8-step expense agent: prompts, conditional oracles, classification.

Design choices (documented because they define what the numbers mean):

- Each step consumes the agent's OWN prior outputs, so wrong values propagate
  exactly as in production.
- Per-step classification compares against the *conditional* oracle (the
  correct answer given the agent's actual inputs), so a step is never blamed
  for errors it inherited.
- If a step ends in a code-detectable failure (format_error or tool_error)
  even after mitigation, the chain substitutes that step's oracle so
  downstream steps remain measurable. The document is an end-to-end
  failure at that point (a production chain has visibly broken there).
  End-to-end success requires no substitutions AND a final summary matching
  ABSOLUTE ground truth.
- Step 5 always receives the full rate table regardless of what step 4
  requested, so step 4 measures tool-calling and step 5 measures arithmetic.
"""

from __future__ import annotations

import json
import re

from failure_lab.realmode.documents import (
    CATEGORIES, RATES, TEMPLATE_CATEGORIES,
)

_JSON_RE = re.compile(r"\{.*\}", re.S)

FORMAT_ERROR = "format_error"
TOOL_ERROR = "tool_error"
WRONG_VALUE = "wrong_value"
INFRA_ERROR = "infra_error"  # transport/runtime failure, not a model failure
SUCCESS = "success"

_NUM_TOL = 0.011


def extract_json(text: str):
    """Best-effort JSON object extraction.

    Strips code fences, then attempts a string-aware parse starting at each
    '{' until one succeeds. Tolerant of prose braces before the object and
    of '}' characters inside JSON strings.
    """
    text = re.sub(r"```(?:json)?", "", text)
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _ = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = text.find("{", idx + 1)
    return None


def _norm(s) -> str:
    return str(s).strip().lower()


def _num_eq(a, b, tol: float = _NUM_TOL) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def _items_by_desc(items) -> dict:
    out = {}
    for it in items:
        out.setdefault(_norm(it.get("description")), it)
    return out


def _duplicate_descs(items) -> bool:
    descs = [_norm(it.get("description")) for it in items]
    return len(descs) != len(set(descs))


def _dedupe_items(parsed):
    """Deduplicate an items list by normalized description (first wins).

    Applied when storing a step's output: a duplicated entry is already
    classified as that step's wrong_value, and deduplicating what flows
    downstream keeps later steps' conditional oracles well-defined instead of
    double-counting the same upstream mistake.
    """
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        return parsed
    seen, items = set(), []
    for it in parsed["items"]:
        key = _norm(it.get("description")) if isinstance(it, dict) else id(it)
        if key not in seen:
            seen.add(key)
            items.append(it)
    return {**parsed, "items": items}


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_ONLY_JSON = ("Respond with ONLY the JSON object: no prose, no markdown, "
              "no explanations. Numbers must be plain (no thousands separators).")


# ---------------------------------------------------------------- step 1
def _p_extract_dates(ctx):
    return (f"{ctx['doc']}\n\n---\nExtract the trip start and end dates from "
            f"the document above.\nJSON schema: "
            f'{{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}}\n{_ONLY_JSON}')


def _o_extract_dates(ctx):
    gt = ctx["gt"]
    return {"start": gt.start.isoformat(), "end": gt.end.isoformat()}


def _e_extract_dates(ctx, parsed, oracle):
    if not isinstance(parsed, dict):
        return FORMAT_ERROR, "no JSON object"
    s, e = parsed.get("start"), parsed.get("end")
    if not (isinstance(s, str) and isinstance(e, str)
            and _DATE_RE.match(s) and _DATE_RE.match(e)):
        return FORMAT_ERROR, "missing/malformed date fields"
    if s != oracle["start"] or e != oracle["end"]:
        return WRONG_VALUE, f"got {s}..{e}, expected {oracle['start']}..{oracle['end']}"
    return SUCCESS, ""


# ---------------------------------------------------------------- step 2
def _p_extract_items(ctx):
    return (f"{ctx['doc']}\n\n---\nList every expense line item in the document "
            f"above.\nJSON schema: "
            f'{{"items": [{{"description": "<text>", "amount": <number>, '
            f'"currency": "THB"|"USD"|"EUR"}}]}}\n'
            f"Copy descriptions exactly as written (without the dots). "
            f"Include only items actually being claimed for reimbursement. "
            f"Exclude any line marked VOIDED, cancelled, or not claimable. "
            f"{_ONLY_JSON}")


def _o_extract_items(ctx):
    return {"items": [{"description": i.description, "amount": i.amount,
                       "currency": i.currency} for i in ctx["gt"].items]}


def _items_shape_ok(parsed, keys) -> bool:
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        return False
    for it in parsed["items"]:
        if not isinstance(it, dict) or not all(k in it for k in keys):
            return False
    return True


def _e_extract_items(ctx, parsed, oracle):
    if not _items_shape_ok(parsed, ("description", "amount", "currency")):
        return FORMAT_ERROR, "items list malformed"
    for it in parsed["items"]:
        if it.get("currency") not in RATES:
            return FORMAT_ERROR, f"unknown currency {it.get('currency')!r}"
        if not isinstance(it.get("amount"), (int, float)):
            return FORMAT_ERROR, "non-numeric amount"
    if _duplicate_descs(parsed["items"]):
        return WRONG_VALUE, "duplicate item descriptions"
    got, exp = _items_by_desc(parsed["items"]), _items_by_desc(oracle["items"])
    if set(got) != set(exp):
        return WRONG_VALUE, f"item set mismatch ({len(got)} vs {len(exp)})"
    for d, e in exp.items():
        g = got[d]
        if g["currency"] != e["currency"] or not _num_eq(g["amount"], e["amount"]):
            return WRONG_VALUE, f"item {d!r}: {g['amount']} {g['currency']}"
    return SUCCESS, ""


# ---------------------------------------------------------------- step 3
def _p_categorize(ctx):
    items = ctx["out"]["extract_items"]["items"]
    return ("Categorize each expense item into exactly one category.\n"
            "Categories: meals (food and drink) · lodging (hotels, "
            "accommodation) · transport (taxis, rides, trains, rail, transit "
            "passes) · supplies (equipment, materials, printed matter) · "
            "other (fees, badges, visas, baggage).\n"
            f"Items:\n{json.dumps({'items': items}, indent=1)}\n"
            'JSON schema: {"items": [{"description": "<same text>", '
            '"category": "<category>"}]}\n'
            f"Include every item exactly once. {_ONLY_JSON}")


def _o_categorize(ctx):
    truth = {_norm(i.description): i.category for i in ctx["gt"].items}
    out = []
    for it in ctx["out"]["extract_items"]["items"]:
        d = it.get("description", "")
        # Items outside ground truth (e.g. a wrongly-extracted VOIDED line)
        # still have a true category via the template table. The categorize
        # step must never be punished for upstream extraction mistakes.
        cat = truth.get(_norm(d)) or TEMPLATE_CATEGORIES.get(_norm(d), "other")
        out.append({"description": d, "category": cat})
    return {"items": out}


def _e_categorize(ctx, parsed, oracle):
    if not _items_shape_ok(parsed, ("description", "category")):
        return FORMAT_ERROR, "items list malformed"
    for it in parsed["items"]:
        if it.get("category") not in CATEGORIES:
            return FORMAT_ERROR, f"unknown category {it.get('category')!r}"
    if _duplicate_descs(parsed["items"]):
        return WRONG_VALUE, "duplicate item descriptions"
    got, exp = _items_by_desc(parsed["items"]), _items_by_desc(oracle["items"])
    if set(got) != set(exp):
        return WRONG_VALUE, "descriptions mismatch"
    # A description absent from both ground truth and the template table has
    # no defined true category (e.g. an upstream reworded item). Any valid
    # category is accepted, so this step is never charged twice for an
    # upstream mistake it inherited.
    known = {_norm(i.description) for i in ctx["gt"].items} | set(TEMPLATE_CATEGORIES)
    wrong = [d for d in exp
             if d in known and got[d]["category"] != exp[d]["category"]]
    if wrong:
        return WRONG_VALUE, f"miscategorized: {wrong[:3]}"
    return SUCCESS, ""


# ---------------------------------------------------------------- step 4
def _p_request_rates(ctx):
    items = ctx["out"]["extract_items"]["items"]
    return ("You must convert the amounts below to USD. Before converting, "
            "request the exchange rate for each distinct non-USD currency "
            "present, using the tool `exchange_rate`.\n"
            f"Items:\n{json.dumps({'items': items}, indent=1)}\n"
            'JSON schema: {"tool_calls": [{"tool": "exchange_rate", '
            '"args": {"currency": "<code>"}}]}\n'
            "Exactly one call per distinct non-USD currency; do not request "
            f"USD. {_ONLY_JSON}")


def _o_request_rates(ctx):
    needed = sorted({it.get("currency") for it in
                     ctx["out"]["extract_items"]["items"]
                     if it.get("currency") != "USD"})
    return {"tool_calls": [{"tool": "exchange_rate",
                            "args": {"currency": c}} for c in needed]}


def _e_request_rates(ctx, parsed, oracle):
    if not isinstance(parsed, dict) or not isinstance(parsed.get("tool_calls"), list):
        return FORMAT_ERROR, "no tool_calls list"
    for c in parsed["tool_calls"]:
        if not isinstance(c, dict):
            return FORMAT_ERROR, "tool call not an object"
        if c.get("tool") != "exchange_rate" or not isinstance(c.get("args"), dict) \
                or "currency" not in c["args"]:
            return TOOL_ERROR, f"bad call: {json.dumps(c)[:80]}"
    got = sorted(str(c["args"]["currency"]) for c in parsed["tool_calls"])
    exp = sorted(c["args"]["currency"] for c in oracle["tool_calls"])
    if got != exp:
        return TOOL_ERROR, f"requested {got}, needed {exp}"
    return SUCCESS, ""


# ---------------------------------------------------------------- step 5
def _p_convert(ctx):
    items = ctx["out"]["extract_items"]["items"]
    return ("Convert each amount to USD using the exchange rates returned by "
            "the tool. Round every result to 2 decimals.\n"
            f"Exchange rates (per 1 unit, in USD): {json.dumps(RATES)}\n"
            f"Items:\n{json.dumps({'items': items}, indent=1)}\n"
            'JSON schema: {"items": [{"description": "<same text>", '
            '"amount_usd": <number>}]}\n'
            f"Include every item exactly once. {_ONLY_JSON}")


def _o_convert(ctx):
    out = []
    for it in ctx["out"]["extract_items"]["items"]:
        rate = RATES.get(it.get("currency"), 1.0)
        try:
            usd = round(float(it.get("amount", 0)) * rate, 2)
        except (TypeError, ValueError):
            usd = 0.0
        out.append({"description": it.get("description", ""), "amount_usd": usd})
    return {"items": out}


def _e_convert(ctx, parsed, oracle):
    if not _items_shape_ok(parsed, ("description", "amount_usd")):
        return FORMAT_ERROR, "items list malformed"
    if _duplicate_descs(parsed["items"]):
        return WRONG_VALUE, "duplicate item descriptions"
    got, exp = _items_by_desc(parsed["items"]), _items_by_desc(oracle["items"])
    if set(got) != set(exp):
        return WRONG_VALUE, "descriptions mismatch"
    for d in exp:
        if not _num_eq(got[d].get("amount_usd"), exp[d]["amount_usd"]):
            return WRONG_VALUE, (f"{d!r}: got {got[d].get('amount_usd')}, "
                                 f"expected {exp[d]['amount_usd']}")
    return SUCCESS, ""


# ---------------------------------------------------------------- step 6
def _p_sum(ctx):
    return ("Join the two lists below by description, then total the USD "
            "amounts per category. Round to 2 decimals.\n"
            f"Categories:\n{json.dumps(ctx['out']['categorize'], indent=1)}\n"
            f"USD amounts:\n{json.dumps(ctx['out']['convert_amounts'], indent=1)}\n"
            'JSON schema: {"totals": {"<category>": <number>}, '
            '"grand_total": <number>}\n'
            f"Include only categories that appear. {_ONLY_JSON}")


def _o_sum(ctx):
    cats = {_norm(i.get("description")): i.get("category")
            for i in ctx["out"]["categorize"]["items"]}
    totals: dict = {}
    grand = 0.0
    for it in ctx["out"]["convert_amounts"]["items"]:
        c = cats.get(_norm(it.get("description")))
        if c is None:
            continue
        try:
            v = float(it.get("amount_usd", 0))
        except (TypeError, ValueError):
            v = 0.0
        totals[c] = round(totals.get(c, 0) + v, 2)
        grand += v
    return {"totals": totals, "grand_total": round(grand, 2)}


def _e_sum(ctx, parsed, oracle):
    if not isinstance(parsed, dict) or not isinstance(parsed.get("totals"), dict) \
            or "grand_total" not in parsed:
        return FORMAT_ERROR, "missing totals/grand_total"
    if set(parsed["totals"]) != set(oracle["totals"]):
        return WRONG_VALUE, (f"category set {sorted(parsed['totals'])} vs "
                             f"{sorted(oracle['totals'])}")
    for c, v in oracle["totals"].items():
        if not _num_eq(parsed["totals"][c], v, tol=0.02):
            return WRONG_VALUE, f"{c}: got {parsed['totals'][c]}, expected {v}"
    if not _num_eq(parsed["grand_total"], oracle["grand_total"], tol=0.05):
        return WRONG_VALUE, (f"grand_total {parsed['grand_total']} vs "
                             f"{oracle['grand_total']}")
    return SUCCESS, ""


# ---------------------------------------------------------------- step 7
def _p_policy(ctx):
    return ("Check the trip against policy. Definitions: trip length in days "
            "= (end date - start date) as a plain calendar-day difference; "
            "item amounts are the USD amounts given.\n"
            f"Trip dates:\n{json.dumps(ctx['out']['extract_dates'])}\n"
            f"USD amounts:\n{json.dumps(ctx['out']['convert_amounts'], indent=1)}\n"
            f"Grand total: {ctx['out']['sum_categories'].get('grand_total')}\n"
            'JSON schema: {"total_exceeds_2000": true|false, '
            '"any_single_item_over_500": true|false, '
            '"trip_longer_than_7_days": true|false}\n'
            f"{_ONLY_JSON}")


def _o_policy(ctx):
    from datetime import date
    d = ctx["out"]["extract_dates"]

    def _parse(s):
        y, m, dd = str(s).split("-")
        return date(int(y), int(m), int(dd))

    try:
        days = (_parse(d["end"]) - _parse(d["start"])).days
    except (ValueError, KeyError, AttributeError):
        days = 0
    try:
        grand = float(ctx["out"]["sum_categories"].get("grand_total", 0))
    except (TypeError, ValueError):
        grand = 0.0
    amounts = []
    for it in ctx["out"]["convert_amounts"]["items"]:
        try:
            amounts.append(float(it.get("amount_usd", 0)))
        except (TypeError, ValueError):
            pass
    return {"total_exceeds_2000": grand > 2000,
            "any_single_item_over_500": any(a > 500 for a in amounts),
            "trip_longer_than_7_days": days > 7}


def _e_policy(ctx, parsed, oracle):
    keys = list(oracle)
    if not isinstance(parsed, dict) or not all(isinstance(parsed.get(k), bool)
                                               for k in keys):
        return FORMAT_ERROR, "flags missing or non-boolean"
    if set(parsed) != set(keys):
        return FORMAT_ERROR, f"unexpected keys: {sorted(set(parsed) - set(keys))}"
    wrong = [k for k in keys if parsed[k] != oracle[k]]
    if wrong:
        return WRONG_VALUE, f"wrong flags: {wrong}"
    return SUCCESS, ""


# ---------------------------------------------------------------- step 8
def _p_final(ctx):
    return ("Produce the final expense summary from the document and the "
            "results below.\n"
            f"{ctx['doc']}\n---\n"
            f"Trip dates: {json.dumps(ctx['out']['extract_dates'])}\n"
            f"Grand total USD: {ctx['out']['sum_categories'].get('grand_total')}\n"
            f"Policy flags: {json.dumps(ctx['out']['policy_check'])}\n"
            'JSON schema: {"employee": "<full name>", "start": "YYYY-MM-DD", '
            '"end": "YYYY-MM-DD", "grand_total_usd": <number>, '
            '"flags": ["<names of flags that are true, sorted alphabetically>"]}\n'
            f"{_ONLY_JSON}")


_CANONICAL_FLAGS = ("total_exceeds_2000", "any_single_item_over_500",
                    "trip_longer_than_7_days")


def _o_final(ctx):
    flags = sorted(k for k in _CANONICAL_FLAGS
                   if ctx["out"]["policy_check"].get(k) is True)
    return {"employee": ctx["gt"].employee,
            "start": ctx["out"]["extract_dates"].get("start"),
            "end": ctx["out"]["extract_dates"].get("end"),
            "grand_total_usd": ctx["out"]["sum_categories"].get("grand_total"),
            "flags": flags}


def _e_final(ctx, parsed, oracle):
    if not isinstance(parsed, dict) or not isinstance(parsed.get("flags"), list):
        return FORMAT_ERROR, "missing fields"
    for k in ("employee", "start", "end", "grand_total_usd"):
        if k not in parsed:
            return FORMAT_ERROR, f"missing {k}"
    if str(parsed["employee"]).strip() != oracle["employee"]:
        return WRONG_VALUE, f"employee {parsed['employee']!r}"
    if parsed["start"] != oracle["start"] or parsed["end"] != oracle["end"]:
        return WRONG_VALUE, "dates drifted"
    if not _num_eq(parsed["grand_total_usd"], oracle["grand_total_usd"], tol=0.05):
        return WRONG_VALUE, f"grand_total {parsed['grand_total_usd']}"
    if sorted(map(str, parsed["flags"])) != oracle["flags"]:
        return WRONG_VALUE, f"flags {parsed['flags']}"
    return SUCCESS, ""


STEPS = [
    ("extract_dates", _p_extract_dates, _o_extract_dates, _e_extract_dates),
    ("extract_items", _p_extract_items, _o_extract_items, _e_extract_items),
    ("categorize", _p_categorize, _o_categorize, _e_categorize),
    ("request_rates", _p_request_rates, _o_request_rates, _e_request_rates),
    ("convert_amounts", _p_convert, _o_convert, _e_convert),
    ("sum_categories", _p_sum, _o_sum, _e_sum),
    ("policy_check", _p_policy, _o_policy, _e_policy),
    ("final_summary", _p_final, _o_final, _e_final),
]

CODE_DETECTABLE = {FORMAT_ERROR, TOOL_ERROR}


def _verifier_prompt(task_prompt: str, raw_response: str) -> str:
    """Blind LLM verifier: sees the task and the response, never ground truth."""
    return ("You are a strict, independent reviewer of an AI worker's output.\n"
            "TASK GIVEN TO THE WORKER:\n<<<\n" + task_prompt + "\n>>>\n"
            "WORKER'S RESPONSE:\n<<<\n" + raw_response + "\n>>>\n"
            "Independently redo the task. Recompute any arithmetic carefully, "
            "re-check every extracted or derived value against the task input, "
            "and check the required output format. Then respond with ONLY "
            '{"verdict": "pass"} or {"verdict": "fail", "reason": "<short>"}. '
            "No prose outside the JSON.")


def end_to_end_ok(ctx, substitutions: int) -> bool:
    """Success = no oracle substitutions AND final summary matches ABSOLUTE truth."""
    if substitutions:
        return False
    final = ctx["out"].get("final_summary")
    gt = ctx["gt"]
    if not isinstance(final, dict):
        return False
    # The grand-total tolerance covers the worst-case accumulation of the
    # per-step tolerances, so per-step rounding alone can never produce an
    # all-steps-green / end-to-end-fail run.
    grand_tol = _NUM_TOL * len(gt.items) + 0.05
    try:
        return (str(final.get("employee", "")).strip() == gt.employee
                and final.get("start") == gt.start.isoformat()
                and final.get("end") == gt.end.isoformat()
                and _num_eq(final.get("grand_total_usd"), gt.grand_total,
                            tol=grand_tol)
                and sorted(map(str, final.get("flags", []))) == gt.true_flag_names)
    except (TypeError, ValueError):
        return False


def run_chain(client, doc: str, gt, mitigation: str = "none"):
    """Run one document through all 8 steps.

    Returns (records, end_to_end, infra_affected), where infra_affected marks
    a document whose chain hit a transport failure, so reports can exclude it
    from model-quality metrics.
    """
    import time

    ctx = {"doc": doc, "gt": gt, "out": {}, "rates": RATES}
    records = []
    substitutions = 0
    infra_affected = False
    for name, p_fn, o_fn, e_fn in STEPS:
        oracle = o_fn(ctx)
        attempts = 0
        outcome, detail, parsed = FORMAT_ERROR, "", None
        max_attempts = 2 if mitigation in ("retry", "verify") else 1
        latency = 0.0
        verifier_checks = 0
        verifier_flags = 0
        attempt_outcomes = []
        while attempts < max_attempts:
            attempts += 1
            if hasattr(client, "arm"):
                client.arm(name, oracle)
            prompt = p_fn(ctx)
            t0 = time.time()
            try:
                raw = client.complete(prompt)
            except Exception as e:  # transport failure, not the model's fault
                latency += time.time() - t0
                outcome, detail, parsed = INFRA_ERROR, str(e)[:200], None
                break
            latency += time.time() - t0
            parsed = extract_json(raw)
            outcome, detail = e_fn(ctx, parsed, oracle)
            # Every attempt's outcome is logged so a verifier flag on a
            # correct first attempt (false positive) is distinguishable from
            # a flag on a real error (true positive) after the fact.
            attempt_outcomes.append(outcome)
            if outcome in CODE_DETECTABLE:
                continue  # both mitigations retry free on code-detectable failures
            # An LLM verifier reviews the output blind (never sees ground
            # truth); a "fail" verdict buys one corrected attempt.
            if mitigation == "verify" and attempts < max_attempts:
                if hasattr(client, "arm"):
                    client.arm(f"{name}::verify", {"verdict": "pass"})
                t0 = time.time()
                try:
                    vraw = client.complete(_verifier_prompt(prompt, raw))
                except Exception:
                    latency += time.time() - t0
                    break  # verifier infra failure: accept the output as-is
                latency += time.time() - t0
                verifier_checks += 1
                v = extract_json(vraw) or {}
                if str(v.get("verdict", "")).lower() == "fail":
                    verifier_flags += 1
                    continue
            break
        if outcome == INFRA_ERROR:
            infra_affected = True
        if parsed is not None and outcome not in CODE_DETECTABLE \
                and outcome != INFRA_ERROR:
            ctx["out"][name] = _dedupe_items(parsed)
        else:
            ctx["out"][name] = oracle
            substitutions += 1
        records.append({"step": name, "outcome": outcome, "attempts": attempts,
                        "attempt_outcomes": attempt_outcomes,
                        "detail": detail, "latency_s": round(latency, 2),
                        "verifier_checks": verifier_checks,
                        "verifier_flags": verifier_flags})
    return records, end_to_end_ok(ctx, substitutions), infra_affected
