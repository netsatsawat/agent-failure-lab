"""Shared matplotlib chart layer: one style for the notebook, app, and README.

Palette and chart chrome follow a validated light-mode data-viz palette:
categorical slots (blue / orange / aqua) for the three mitigation series,
an ordinal blue ramp for accuracy levels, recessive grid and muted ink.
"""

import matplotlib.pyplot as plt

from failure_lab.model import (
    DEFAULT_VERIFIER_RECALL,
    MITIGATIONS,
    chain_success,
    expected_calls,
)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

SERIES = {"none": "#2a78d6", "verify": "#eb6834", "retry": "#1baf7a"}
BLUE_RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#184f95"]


def _style(ax, xlabel: str, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.75)
    ax.set_axisbelow(True)
    ax.set_xlabel(xlabel, color=MUTED, fontsize=10)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=10)


def _pct_axis(ax) -> None:
    ax.set_ylim(0, 1.02)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])


def collapse_by_accuracy_fig(accuracies=(0.99, 0.95, 0.90, 0.85), max_steps: int = 15):
    """End-to-end success vs chain length, one line per per-step accuracy."""
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    steps = range(1, max_steps + 1)
    for color, acc in zip(BLUE_RAMP, sorted(accuracies)):
        ys = [chain_success(acc, n) for n in steps]
        ax.plot(steps, ys, color=color, linewidth=2, label=f"{acc:.0%} per step")
        ax.annotate(f"{acc:.0%}", xy=(max_steps, ys[-1]),
                    xytext=(max_steps + 0.3, ys[-1]), color=color,
                    fontsize=9, va="center")
    _style(ax, "steps in the chain", "end-to-end success")
    _pct_axis(ax)
    ax.set_xlim(1, max_steps + 1.8)
    ax.set_title("Per-step accuracy compounds against you",
                 color=INK, fontsize=12, loc="left")
    ax.legend(frameon=False, labelcolor=MUTED, fontsize=9, loc="lower left")
    fig.tight_layout()
    return fig


def mitigation_fig(p: float = 0.85, max_steps: int = 15,
                   verifier_recall: float = DEFAULT_VERIFIER_RECALL):
    """End-to-end success vs chain length for none / verify / retry."""
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    steps = range(1, max_steps + 1)
    for m in MITIGATIONS:
        ys = [chain_success(p, n, m, verifier_recall) for n in steps]
        ax.plot(steps, ys, color=SERIES[m], linewidth=2, label=m)
        ax.annotate(m, xy=(max_steps, ys[-1]),
                    xytext=(max_steps + 0.3, ys[-1]), color=SERIES[m],
                    fontsize=9, va="center")
    ten = chain_success(p, 10)
    ax.annotate(f"{ten:.1%} at 10 steps", xy=(10, ten), xytext=(10.4, ten + 0.12),
                color=INK, fontsize=9,
                arrowprops={"arrowstyle": "-", "color": BASELINE})
    _style(ax, "steps in the chain", "end-to-end success")
    _pct_axis(ax)
    ax.set_xlim(1, max_steps + 2.2)
    ax.set_title(f"Mitigations at {p:.0%} per-step accuracy",
                 color=INK, fontsize=12, loc="left")
    ax.legend(frameon=False, labelcolor=MUTED, fontsize=9, loc="lower left")
    fig.tight_layout()
    return fig


def cost_fig(p: float = 0.85, steps: int = 10,
             verifier_recall: float = DEFAULT_VERIFIER_RECALL):
    """Reliability vs cost: end-to-end success against expected LLM calls."""
    fig, ax = plt.subplots(figsize=(7, 4.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    for m in MITIGATIONS:
        x = expected_calls(p, steps, m, verifier_recall)
        y = chain_success(p, steps, m, verifier_recall)
        ax.scatter([x], [y], s=90, color=SERIES[m], zorder=3, label=m)
        ax.annotate(f"{m}\n{y:.0%} for {x:.1f} calls", xy=(x, y),
                    xytext=(x + 0.5, y - 0.02), color=SERIES[m], fontsize=9)
    _style(ax, f"expected LLM calls for a {steps}-step chain", "end-to-end success")
    _pct_axis(ax)
    ax.set_xlim(0, expected_calls(p, steps, "verify", verifier_recall) + 8)
    ax.set_title("What reliability costs in LLM calls",
                 color=INK, fontsize=12, loc="left")
    ax.legend(frameon=False, labelcolor=MUTED, fontsize=9, loc="lower right")
    fig.tight_layout()
    return fig
