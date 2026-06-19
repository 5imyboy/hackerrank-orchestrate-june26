"""Wrap the Anthropic vision call: one Claude Opus 4.8 request per claim.

Design choices:
- model = claude-opus-4-8 (default, most capable Opus-tier).
- adaptive thinking on (the sample cases need real reasoning).
- streaming + get_final_message() so multi-image calls don't hit a timeout.
- system prompt sent with cache_control so its tokens are billed once and reused.
- JSON-in-text output, parsed + validated with the Pydantic model.
- usage (incl. cache + thinking tokens) is returned for the cost report.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import anthropic

from .data import Case
from .prompt import SYSTEM_PROMPT, build_user_content
from .schema import ClaimAssessment

MODEL = "claude-opus-4-8"
MAX_TOKENS = 2048


@dataclass
class Usage:
    """Token counters for one call (summed later for the cost report)."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def add(self, other: "Usage") -> None:
        """In-place accumulate. `+=` on ints rebinds (ints are immutable)."""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens


@dataclass
class CallResult:
    """What a single assessment returns: the parsed answer + its token usage."""
    assessment: ClaimAssessment
    usage: Usage


def make_client() -> anthropic.Anthropic:
    """Build the SDK client. The key is read from ANTHROPIC_API_KEY by default.

    max_retries lets the SDK itself retry transient 429/5xx with backoff; we add
    one extra retry layer in assess_case for resilience during a long batch run.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy code/.env.example to code/.env "
            "and add your key (or export it in the shell)."
        )
    return anthropic.Anthropic(max_retries=4)


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of the model's final text.

    The model is told to emit only JSON, but we defensively strip markdown fences
    and slice from the first '{' to the last '}' before json.loads.
    """
    t = text.strip()
    if t.startswith("```"):
        # remove a leading ```json / ``` fence and the trailing fence
        t = t.split("```", 2)[-1] if t.count("```") >= 2 else t.strip("`")
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model output: {text[:200]!r}")
    return json.loads(t[start : end + 1])


def _final_text(message) -> str:
    """Concatenate the text blocks of a message (skipping thinking blocks)."""
    parts = [b.text for b in message.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts)


def _usage_from(message) -> Usage:
    u = message.usage
    # getattr(obj, name, default) ~= a null-safe field read with a fallback.
    return Usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
    )


def assess_case(
    client: anthropic.Anthropic,
    case: Case,
    max_attempts: int = 3,
) -> CallResult:
    """Run one claim through Claude vision and return a validated assessment."""
    # system is a list of blocks so we can attach cache_control to the big,
    # constant prompt. "ephemeral" cache lives ~5 min — plenty for one batch run.
    system = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    messages = [{"role": "user", "content": build_user_content(case)}]

    last_err: Exception | None = None
    for attempt in range(max_attempts):  # range(3) -> 0,1,2
        try:
            # Streaming context manager; get_final_message() blocks until done.
            with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,
                thinking={"type": "adaptive"},
            ) as stream:
                message = stream.get_final_message()

            data = _extract_json(_final_text(message))
            assessment = ClaimAssessment.model_validate(data)
            return CallResult(assessment=assessment, usage=_usage_from(message))

        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            # transient API problem: exponential backoff then retry
            last_err = e
            time.sleep(2 ** attempt)
        except (ValueError, json.JSONDecodeError) as e:
            # the model returned unparseable output: retry (often transient)
            last_err = e
            time.sleep(1)

    raise RuntimeError(
        f"assess_case failed for user={case.user_id} after {max_attempts} "
        f"attempts: {last_err}"
    )
