"""Shared concurrency + cost helpers, reused by main.py and evaluation/main.py."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from .client import CallResult, Usage, assess_case
from .data import Case
from .normalize import error_row, to_output_row

# Claude Opus 4.8 pricing (USD per 1M tokens), per the model table.
PRICE_INPUT = 5.00
PRICE_OUTPUT = 25.00
PRICE_CACHE_WRITE = PRICE_INPUT * 1.25   # cache creation costs 1.25x base input
PRICE_CACHE_READ = PRICE_INPUT * 0.10    # cache hits cost 0.10x base input


def estimate_cost(u: Usage) -> float:
    """USD estimate from accumulated token usage."""
    return (
        u.input_tokens * PRICE_INPUT
        + u.output_tokens * PRICE_OUTPUT
        + u.cache_creation_input_tokens * PRICE_CACHE_WRITE
        + u.cache_read_input_tokens * PRICE_CACHE_READ
    ) / 1_000_000  # underscores in numbers are just visual separators


def process_cases(
    client: anthropic.Anthropic,
    cases: list[Case],
    workers: int = 6,
) -> tuple[list[dict[str, str]], Usage]:
    """Assess every case concurrently; return rows IN INPUT ORDER + total usage.

    A ThreadPoolExecutor is fine here because each task is I/O-bound (waiting on
    the network), so the GIL is released during the call — similar to a Java
    fixed thread pool issuing blocking HTTP requests.
    """
    rows: list[dict[str, str] | None] = [None] * len(cases)  # pre-sized slots
    total = Usage()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        # submit() returns a Future; we remember which index each Future fills.
        future_to_idx = {
            pool.submit(assess_case, client, case): idx
            for idx, case in enumerate(cases)  # enumerate ~= indexed for-loop
        }
        done = 0
        for future in as_completed(future_to_idx):  # yields as each finishes
            idx = future_to_idx[future]
            case = cases[idx]
            try:
                result: CallResult = future.result()
                rows[idx] = to_output_row(case, result.assessment)
                total.add(result.usage)
            except Exception as e:  # never let one bad claim sink the batch
                rows[idx] = error_row(case, str(e))
            done += 1
            # \r returns the cursor to line start for an updating progress line.
            print(f"\r  processed {done}/{len(cases)} claims", end="", file=sys.stderr)

    print("", file=sys.stderr)  # newline after the progress line
    # mypy/readers: every slot is filled by now; cast away the Optional.
    return [r for r in rows if r is not None], total
