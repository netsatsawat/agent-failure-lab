"""Streamlit showcase for compound failure in multi-step AI agents.

Run: streamlit run app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from failure_lab.charts import cost_fig, mitigation_fig
from failure_lab.model import (
    MITIGATIONS,
    chain_success,
    expected_calls,
    required_step_accuracy,
)

st.set_page_config(page_title="agent-failure-lab", page_icon="📉", layout="wide")

st.title("Watch compound error kill your AI agent")
st.caption(
    "Companion app for *Why Your AI Agent Will Fail* · "
    "[satsawat.ai](https://satsawat.ai) · "
    "[AI in Practice newsletter](https://satsawat.ai/#newsletter)"
)

with st.sidebar:
    st.header("Your agent")
    accuracy = st.slider("Per-step accuracy", 0.50, 1.00, 0.85, 0.01,
                         format="%.2f")
    steps = st.slider("Steps in the chain", 1, 25, 10)
    recall = st.slider("Verifier recall", 0.50, 1.00, 0.90, 0.05,
                       help="How often an LLM verifier catches a failed step.")
    target = st.slider("Target end-to-end success", 0.50, 0.99, 0.90, 0.01,
                       format="%.2f")
    st.markdown(
        "**Mitigations**\n\n"
        "- `none`: failures go undetected\n"
        "- `verify`: an LLM verifier reviews every step "
        "(+1 call/step), caught failures get one corrected attempt\n"
        "- `retry`: code-detectable failures (schema, tool errors) "
        "get one free retry"
    )

c1, c2, c3 = st.columns(3)
for col, m in zip((c1, c2, c3), MITIGATIONS):
    success = chain_success(accuracy, steps, m, recall)
    calls = expected_calls(accuracy, steps, m, recall)
    col.metric(
        label=f"{m}: end-to-end success",
        value=f"{success:.1%}",
        delta=f"{calls:.1f} expected LLM calls",
        delta_color="off",
    )

left, right = st.columns(2)
with left:
    st.pyplot(mitigation_fig(accuracy, max(15, steps + 3), recall))
with right:
    st.pyplot(cost_fig(accuracy, steps, recall))

st.divider()

needed = required_step_accuracy(target, steps)
st.subheader("The reliability budget")
st.markdown(
    f"To hit **{target:.0%} end-to-end success over {steps} steps**, every "
    f"step needs **{needed:.2%}** accuracy before any mitigation. "
    f"At your current **{accuracy:.0%}**, the gap is what `verify` and "
    f"`retry` exist to close. The uncomfortable takeaway: past a handful of "
    f"steps, reliability is an *architecture* property, not a model property."
)

st.caption(
    "Analytic model. See the notebook for Monte Carlo agreement and the "
    "full walkthrough, and `python realmode.py run` for the same experiment "
    "against a real local model with a logged failure taxonomy (results in "
    "`runs/`)."
)
