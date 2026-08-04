"""LLM clients for real mode: Ollama (stdlib HTTP) and a deterministic mock.

MockClient is oracle-based: it computes the correct answer for each step from
the same conditional-truth functions the classifier uses, then optionally
injects failures — which makes the whole pipeline testable without a model.
"""

from __future__ import annotations

import json
import re
import urllib.request


class OllamaClient:
    """Minimal Ollama /api/generate client. No third-party dependencies.

    Deliberately does NOT use Ollama's format="json" constrained decoding:
    real mode wants the model's natural format-error rate, not a sanitized one.
    """

    def __init__(self, model: str = "qwen3.6:27b",
                 host: str = "http://localhost:11434",
                 temperature: float = 0.2, num_predict: int = 700,
                 timeout: int = 1800):
        self.model = model
        self.host = host.rstrip("/")
        self.temperature = temperature
        self.num_predict = num_predict
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": self.temperature,
                        "num_predict": self.num_predict},
        }
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        last_err = None
        for _ in range(2):  # one transparent retry on transport failures
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read())
                text = body.get("response", "")
                # Defensive: strip thinking traces if the model emits them anyway.
                return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
            except OSError as e:  # socket.timeout, URLError, ConnectionError
                last_err = e
        raise RuntimeError(f"ollama request failed after retry: {last_err}")


class MockClient:
    """Oracle mock with failure injection, for tests and dry runs.

    ``inject`` maps step name -> one of:
      "garbage"       : return unparseable text (format_error)
      "wrong_tool"    : return a bad tool call (tool_error, step 'request_rates')
      "wrong_value"   : return well-formed JSON with corrupted numbers/values
    ``fail_first_attempt_only`` makes injected failures succeed on retry.
    ``verifier_verdicts`` maps step name -> list of verdicts ("pass"/"fail")
    consumed in order by the verify mitigation's checks; default is "pass".
    """

    def __init__(self, inject: dict | None = None,
                 fail_first_attempt_only: bool = False,
                 verifier_verdicts: dict | None = None):
        self.inject = inject or {}
        self.fail_first_attempt_only = fail_first_attempt_only
        self._verdicts_template = {k: list(v) for k, v in
                                   (verifier_verdicts or {}).items()}
        self.verifier_verdicts = {k: list(v) for k, v in
                                  self._verdicts_template.items()}
        self._attempts: dict = {}
        self._oracle_answer = None  # set by the runner before each call
        self._step_name = None

    def begin_doc(self, doc_id: int) -> None:
        """Reset per-document attempt counters and verdict queues."""
        self._attempts = {}
        self.verifier_verdicts = {k: list(v) for k, v in
                                  self._verdicts_template.items()}

    def arm(self, step_name: str, oracle_answer: dict) -> None:
        """The runner arms the mock with the correct answer for the next call."""
        self._step_name = step_name
        self._oracle_answer = oracle_answer

    def complete(self, prompt: str) -> str:
        step = self._step_name
        if step and step.endswith("::verify"):
            base = step[: -len("::verify")]
            queue = self.verifier_verdicts.get(base)
            verdict = queue.pop(0) if queue else "pass"
            return json.dumps({"verdict": verdict})
        key = step
        self._attempts[key] = self._attempts.get(key, 0) + 1
        mode = self.inject.get(step)
        if mode and self.fail_first_attempt_only and self._attempts[key] > 1:
            mode = None
        if mode == "garbage":
            return "Sure! Here is what I found — the trip looks reasonable overall."
        if mode == "wrong_tool":
            return json.dumps({"tool_calls": [
                {"tool": "currency_lookup", "args": {"code": "THB"}}]})
        if mode == "wrong_value":
            corrupted = json.loads(json.dumps(self._oracle_answer))
            _corrupt_numbers(corrupted)
            return json.dumps(corrupted)
        return json.dumps(self._oracle_answer)


def _corrupt_numbers(obj) -> bool:
    """Multiply the first number found by 10 (in place). Returns True if done."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                obj[k] = round(v * 10 + 1, 2)
                return True
            if _corrupt_numbers(v):
                return True
    elif isinstance(obj, list):
        for v in obj:
            if _corrupt_numbers(v):
                return True
    return False
