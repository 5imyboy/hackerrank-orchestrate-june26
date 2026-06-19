"""Entry point: read dataset/claims.csv, run the pipeline, write output.csv.

Usage:
    python code/main.py                      # full run -> output.csv at repo root
    python code/main.py --limit 5            # smoke test on the first 5 claims
    python code/main.py --claims path.csv --out preds.csv --workers 8

Secrets: reads ANTHROPIC_API_KEY from the environment (or code/.env). Never hardcoded.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

# Make "claim_pipeline" importable whether you run this from the repo root or
# from inside code/. We add the directory containing this file to sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402  (import after sys.path tweak)

from claim_pipeline.client import make_client  # noqa: E402
from claim_pipeline.data import DATASET_DIR, REPO_ROOT, build_cases  # noqa: E402
from claim_pipeline.runner import estimate_cost, process_cases  # noqa: E402
from claim_pipeline.schema import OUTPUT_COLUMNS  # noqa: E402


def write_output(rows: list[dict[str, str]], out_path: Path) -> None:
    """Write rows to CSV with the exact required column order, all fields quoted."""
    with out_path.open("w", newline="", encoding="utf-8") as f:
        # QUOTE_ALL matches the dataset's style (every field wrapped in quotes).
        writer = csv.DictWriter(
            f, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    """argparse ~= a CLI flag parser (like picocli/JCommander in Java)."""
    p = argparse.ArgumentParser(description="Multi-modal damage claim verifier")
    p.add_argument(
        "--claims",
        type=Path,
        default=DATASET_DIR / "claims.csv",
        help="Input claims CSV (default: dataset/claims.csv)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "output.csv",
        help="Output CSV path (default: output.csv at repo root)",
    )
    p.add_argument("--workers", type=int, default=6, help="Concurrent API calls")
    p.add_argument(
        "--limit", type=int, default=0, help="Process only the first N claims (0=all)"
    )
    return p.parse_args()


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env")  # load code/.env if present
    args = parse_args()

    cases = build_cases(args.claims)
    if args.limit:
        cases = cases[: args.limit]  # list slice ~= subList(0, limit)

    n_images = sum(len(c.images) for c in cases)  # sum() over a generator
    print(f"Loaded {len(cases)} claims, {n_images} images.", file=sys.stderr)

    client = make_client()
    start = time.time()
    rows, usage = process_cases(client, cases, workers=args.workers)
    elapsed = time.time() - start

    write_output(rows, args.out)

    # Operational summary (also informs evaluation_report.md).
    print(f"\nWrote {len(rows)} rows -> {args.out}", file=sys.stderr)
    print(f"Runtime: {elapsed:.1f}s ({elapsed / max(len(rows),1):.1f}s/claim)", file=sys.stderr)
    print(
        "Tokens — input: {ip:,}  output: {op:,}  cache_write: {cw:,}  cache_read: {cr:,}".format(
            ip=usage.input_tokens, op=usage.output_tokens,
            cw=usage.cache_creation_input_tokens, cr=usage.cache_read_input_tokens,
        ),
        file=sys.stderr,
    )
    print(f"Estimated cost: ${estimate_cost(usage):.4f}", file=sys.stderr)


# This guard means main() runs only when the file is executed directly, not when
# imported. It's the Python equivalent of `public static void main`.
if __name__ == "__main__":
    main()
