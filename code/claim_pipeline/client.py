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
# Adaptive thinking tokens count against max_tokens, so this budget must cover
# the model's reasoning PLUS the JSON answer. 2048 truncated the JSON on
# harder cases (the response was cut off mid-object and failed to parse), so we
# give generous headroom. Output is billed per token actually used, so a high
# cap costs nothing extra when the response is short.
MAX_TOKENS = 8000

# The system prompt is identical for every claim, so we build the cached block
# ONCE at import time and reuse it on every call. cache_control marks it so
# Anthropic caches it server-side: the first call pays full input price, the
# rest (within ~5 min) read it back at ~10% cost.
SYSTEM_BLOCKS = [
    {
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }
]


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
    # Strip a ```json ... ``` fence if the model added one. We just remove all
    # triple-backtick markers and the optional "json" tag, then slice the braces.
    t = t.replace("```json", "").replace("```", "").strip()
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
    # SYSTEM_BLOCKS (built once at import) carries the cached rule block; only the
    # per-claim user message is assembled here.
    messages = [{"role": "user", "content": build_user_content(case)}]

    last_err: Exception | None = None
    for attempt in range(max_attempts):  # range(3) -> 0,1,2
        try:
            # Streaming context manager; get_final_message() blocks until done.
            with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_BLOCKS,
                messages=messages,
                thinking={"type": "adaptive"},
            ) as stream:
                message = stream.get_final_message()

            # If the model hit the token ceiling, the JSON is likely cut off.
            # Surface it as a retryable error rather than a confusing parse fail.
            if message.stop_reason == "max_tokens":
                raise ValueError("response truncated at max_tokens")

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
