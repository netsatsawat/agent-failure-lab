"""Real mode: an actual multi-step agent on a local model, with logged,
classified failures.

The pipeline processes synthetic expense reports (known ground truth) through
8 LLM steps. Each step consumes the agent's OWN prior outputs, so errors
compound exactly as in production. Per-step outcomes are classified against
*conditional* ground truth (the correct answer given the agent's actual
inputs), which isolates each step's skill from inherited errors.
End-to-end success is judged against absolute ground truth.

Failure taxonomy per step attempt:
- format_error : output is not parseable JSON of the required shape (code-detectable)
- tool_error   : wrong/missing tool call (code-detectable)
- wrong_value  : well-formed but factually wrong vs conditional truth (needs
                 ground truth or a verifier to catch: the hallucination class)
"""
