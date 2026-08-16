"""Aggregate a real-mode JSONL run into a markdown report + taxonomy chart."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from failure_lab.realmode.agent import STEPS

OUTCOMES = ("success", "wrong_value", "format_error", "tool_error", "infra_error")

# Status palette (semantic, not series colors): good / warning / serious / critical
_COLORS = {"success": "#0ca30c", "wrong_value": "#d03b3b",
           "format_error": "#fab219", "tool_error": "#ec835a",
           "infra_error": "#898781"}
_SURFACE = "#fcfcfb"
_INK = "#0b0b0b"
_MUTED = "#898781"


def load_run(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def aggregate(records: list[dict]) -> dict:
    if not records:
        raise ValueError("run file contains no records (aborted run?)")
    steps = [s[0] for s in STEPS]
    # A document that hit a transport failure is excluded as a whole: the rest
    # of its steps ran in a chain that was already broken, so they are not
    # evidence about model quality either. Only the infra_error record itself
    # stays, so the taxonomy still shows where transport failed.
    infra_ids = {r.get("doc_id") for r in records
                 if r.get("infra_affected") or r["outcome"] == "infra_error"}
    per_step: dict = {s: defaultdict(int) for s in steps}
    e2e = defaultdict(int)
    retried = 0
    infra_docs = 0
    verifier_checks = 0
    verifier_flags = 0
    for r in records:
        if r["step"] == "__end_to_end__":
            if r.get("infra_affected"):
                infra_docs += 1  # infrastructure failure, not model quality
            else:
                e2e[r["outcome"]] += 1
        elif r.get("doc_id") in infra_ids and r["outcome"] != "infra_error":
            continue  # excluded document: only its infra_error stays visible
        else:
            per_step[r["step"]][r["outcome"]] += 1
            if r.get("attempts", 1) > 1:
                retried += 1
            verifier_checks += r.get("verifier_checks", 0)
            verifier_flags += r.get("verifier_flags", 0)
    n_docs = sum(e2e.values())
    # Per-step success is a model-quality metric: infra errors are excluded
    # from the denominator rather than counted against the model.
    step_rates = {}
    for s in steps:
        row = per_step[s]
        denom = sum(row.values()) - row.get("infra_error", 0)
        step_rates[s] = row["success"] / max(1, denom)
    predicted = 1.0
    for v in step_rates.values():
        predicted *= v
    return {"steps": steps, "per_step": {s: dict(per_step[s]) for s in steps},
            "step_rates": step_rates, "n_docs": n_docs, "retried_steps": retried,
            "infra_docs": infra_docs, "verifier_checks": verifier_checks,
            "verifier_flags": verifier_flags,
            "observed_e2e": e2e["success"] / max(1, n_docs),
            "predicted_e2e": predicted}


def taxonomy_chart(agg: dict, out_png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    steps = agg["steps"]
    n = [sum(agg["per_step"][s].values()) or 1 for s in steps]
    fig, ax = plt.subplots(figsize=(8, 4.4), dpi=150)
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)
    bottom = [0.0] * len(steps)
    for outcome in OUTCOMES:
        vals = [agg["per_step"][s].get(outcome, 0) / n[i]
                for i, s in enumerate(steps)]
        ax.bar(range(len(steps)), vals, bottom=bottom, width=0.62,
               color=_COLORS[outcome], label=outcome.replace("_", " "),
               edgecolor=_SURFACE, linewidth=2)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xticks(range(len(steps)))
    ax.set_xticklabels([s.replace("_", "\n") for s in steps],
                       fontsize=8, color=_MUTED)
    ax.set_ylim(0, 1.001)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"],
                       fontsize=9, color=_MUTED)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=_MUTED, length=0)
    ax.set_title("Per-step outcome taxonomy (real local-model agent)",
                 color=_INK, fontsize=12, loc="left")
    ax.legend(frameon=False, labelcolor=_MUTED, fontsize=9,
              loc="lower left", ncol=4, bbox_to_anchor=(0, -0.32))
    fig.tight_layout()
    fig.savefig(out_png, facecolor=_SURFACE, bbox_inches="tight")
    plt.close(fig)


def render_report(agg: dict, meta: dict, out_md: Path,
                  chart_rel: str | None) -> None:
    L = ["# Real-mode report", ""]
    hard = " · hard documents" if meta.get("hard") else ""
    L.append(f"Model: **{meta.get('model', '?')}** · documents: "
             f"**{agg['n_docs']}**{hard} · mitigation: "
             f"**{meta.get('mitigation')}** · steps retried: "
             f"{agg['retried_steps']}")
    if agg.get("infra_docs"):
        L.append("")
        L.append(f"({agg['infra_docs']} document(s) excluded from all metrics "
                 "due to infrastructure failures; see the infra error column)")
    if agg.get("verifier_checks"):
        L.append("")
        L.append(f"Verifier: {agg['verifier_checks']} checks, "
                 f"{agg['verifier_flags']} flags raised.")
    L.append("")
    if chart_rel:
        L += [f"![Per-step outcome taxonomy]({chart_rel})", ""]
    L += ["| step | success | wrong value | format error | tool error | infra error |",
          "|---|---|---|---|---|---|"]
    for s in agg["steps"]:
        row = agg["per_step"][s]
        total = max(1, sum(row.values()))
        L.append("| " + " | ".join(
            [s] + [f"{row.get(o, 0) / total:.0%}" for o in OUTCOMES]) + " |")
    L += ["",
          f"**Observed end-to-end success: {agg['observed_e2e']:.0%}** · "
          f"predicted from measured per-step rates (independence assumption): "
          f"{agg['predicted_e2e']:.0%}",
          "",
          "Per-step outcomes are judged against *conditional* ground truth "
          "(correct given the agent's own prior outputs); end-to-end is judged "
          "against absolute ground truth. `format_error` and `tool_error` are "
          "code-detectable, so the `retry` mitigation applies. `wrong_value` is "
          "the hallucination class: only a verifier or ground truth catches it."]
    out_md.write_text("\n".join(L) + "\n")
