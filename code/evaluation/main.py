"""Evaluate the pipeline against dataset/sample_claims.csv (which has gold labels).

Runs the SAME pipeline used for the real test set, then scores predictions
against the labeled columns. Outputs:
  - evaluation/predictions_sample.csv  (model predictions on the sample)
  - evaluation/metrics.json            (machine-readable scores)
  - console report                     (per-field accuracy, confusion, flag F1)

Usage:
    python code/evaluation/main.py
    python code/evaluation/main.py --limit 5
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

# code/evaluation/main.py -> parent is evaluation/, parent.parent is code/.
CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))

from dotenv import load_dotenv  # noqa: E402

from claim_pipeline.client import make_client  # noqa: E402
from claim_pipeline.data import DATASET_DIR, build_cases  # noqa: E402
from claim_pipeline.runner import estimate_cost, process_cases  # noqa: E402
from claim_pipeline.schema import OUTPUT_COLUMNS  # noqa: E402

HERE = Path(__file__).resolve().parent
SAMPLE_CSV = DATASET_DIR / "sample_claims.csv"

# Categorical fields we score with exact-match accuracy.
EXACT_FIELDS = [
    "evidence_standard_met", "valid_image", "claim_status",
    "issue_type", "object_part", "severity",
]


def read_gold(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def flag_set(value: str) -> set[str]:
    """Parse a 'a;b;c' risk_flags cell into a set, dropping 'none'."""
    return {t.strip() for t in value.split(";") if t.strip() and t.strip() != "none"}


def score(preds: list[dict[str, str]], gold: list[dict[str, str]]) -> dict:
    """Compute per-field accuracy, claim_status confusion, and risk-flag F1."""
    n = len(preds)
    # exact-match counters per field
    correct = {field: 0 for field in EXACT_FIELDS}
    # confusion[gold_label][pred_label] = count
    labels = ["supported", "contradicted", "not_enough_information"]
    confusion = {g: {p: 0 for p in labels} for g in labels}
    # micro counts for risk-flag set comparison
    tp = fp = fn = 0

    for pred, g in zip(preds, gold):  # zip ~= iterate two lists in lockstep
        for field in EXACT_FIELDS:
            if pred[field].strip().lower() == g[field].strip().lower():
                correct[field] += 1

        gs, ps = g["claim_status"].strip(), pred["claim_status"].strip()
        if gs in confusion and ps in confusion[gs]:
            confusion[gs][ps] += 1

        gp, pp = flag_set(g["risk_flags"]), flag_set(pred["risk_flags"])
        tp += len(pp & gp)   # set intersection
        fp += len(pp - gp)   # in prediction, not in gold
        fn += len(gp - pp)   # in gold, missed

    accuracy = {field: correct[field] / n for field in EXACT_FIELDS}
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "n": n,
        "accuracy": accuracy,
        "claim_status_confusion": confusion,
        "risk_flags": {"precision": precision, "recall": recall, "f1": f1,
                       "tp": tp, "fp": fp, "fn": fn},
    }


def print_report(metrics: dict) -> None:
    print("\n=== Evaluation on sample_claims.csv ===")
    print(f"claims scored: {metrics['n']}\n")
    print("Per-field exact-match accuracy:")
    for field, acc in metrics["accuracy"].items():
        print(f"  {field:<24} {acc * 100:5.1f}%")

    print("\nclaim_status confusion (rows=gold, cols=pred):")
    labels = ["supported", "contradicted", "not_enough_information"]
    header = " " * 24 + "".join(f"{l[:12]:>14}" for l in labels)
    print(header)
    for g in labels:
        cells = "".join(f"{metrics['claim_status_confusion'][g][p]:>14}" for p in labels)
        print(f"  {g:<22}{cells}")

    rf = metrics["risk_flags"]
    print("\nrisk_flags (micro over flag tokens):")
    print(f"  precision {rf['precision']*100:5.1f}%  recall {rf['recall']*100:5.1f}%  "
          f"f1 {rf['f1']*100:5.1f}%  (tp={rf['tp']} fp={rf['fp']} fn={rf['fn']})")


def write_predictions(rows: list[dict[str, str]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)


def _headline_table(
    lines: list[str],
    preds: list[dict[str, str]],
    gold: list[dict[str, str]],
    field: str,
    title: str,
) -> None:
    """Append a one-row-per-case gold-vs-pred table for `field` to `lines`.

    `lines` is mutated in place (Python lists are passed by reference, like a
    Java object reference), so there is nothing to return.
    """
    lines.append(f"## {title}")
    lines.append("")
    lines.append("| user_id | object | gold | pred | ok |")
    lines.append("|---|---|---|---|---|")
    for p, g in zip(preds, gold):
        ok = "✓" if p[field].strip().lower() == g[field].strip().lower() else "✗"
        lines.append(f"| {g['user_id']} | {g['claim_object']} | "
                     f"{g[field]} | {p[field]} | {ok} |")
    lines.append("")


def write_diff(
    preds: list[dict[str, str]],
    gold: list[dict[str, str]],
    metrics: dict,
    path: Path,
) -> None:
    """Write a human-readable per-case diff (Markdown) so misses are easy to see.

    Reads nothing new — it just formats the predictions we already have against
    the gold rows. `lines` is a list[str] we join at the end (cheaper than
    repeated string concatenation, ~= a StringBuilder).
    """
    lines: list[str] = ["# Sample evaluation — per-case diff", ""]

    # --- summary block ---
    lines.append(f"- claims scored: **{metrics['n']}**")
    lines.append(f"- runtime: {metrics.get('runtime_seconds', '?')}s  "
                 f"cost: ${metrics.get('estimated_cost_usd', '?')}")
    lines.append("- per-field exact-match accuracy:")
    for field, acc in metrics["accuracy"].items():
        lines.append(f"    - {field}: {acc * 100:.1f}%")
    rf = metrics["risk_flags"]
    lines.append(f"- risk_flags micro: P {rf['precision']*100:.1f}%  "
                 f"R {rf['recall']*100:.1f}%  F1 {rf['f1']*100:.1f}%")
    lines.append("")

    # --- per-field headline tables (claim_status, then issue_type) ---
    _headline_table(lines, preds, gold, "claim_status", "claim_status (headline)")
    _headline_table(lines, preds, gold, "issue_type", "issue_type (headline)")

    # --- per-case field misses ---
    lines.append("## Per-case misses (only cases with at least one wrong field)")
    lines.append("")
    any_miss = False
    for p, g in zip(preds, gold):
        misses: list[str] = []
        for field in EXACT_FIELDS:
            if p[field].strip().lower() != g[field].strip().lower():
                misses.append(f"  - {field}: `{g[field]}` → `{p[field]}`")

        # risk-flag set diff (what we added vs. what we missed)
        gp, pp = flag_set(g["risk_flags"]), flag_set(p["risk_flags"])
        extra, missing = pp - gp, gp - pp
        if extra or missing:
            parts = []
            if extra:
                parts.append("+" + ",".join(sorted(extra)))
            if missing:
                parts.append("-" + ",".join(sorted(missing)))
            misses.append(f"  - risk_flags: {' '.join(parts)}")

        if misses:
            any_miss = True
            lines.append(f"**{g['user_id']}** ({g['claim_object']}):")
            lines.extend(misses)
            lines.append("")

    if not any_miss:
        lines.append("_No field misses — perfect run._")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    load_dotenv(CODE_DIR / ".env")
    parser = argparse.ArgumentParser(description="Evaluate on sample_claims.csv")
    parser.add_argument("--limit", type=int, default=0, help="First N samples (0=all)")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    cases = build_cases(SAMPLE_CSV)
    gold = read_gold(SAMPLE_CSV)
    if args.limit:
        cases, gold = cases[: args.limit], gold[: args.limit]

    print(f"Evaluating on {len(cases)} sample claims...", file=sys.stderr)
    client = make_client()
    start = time.time()
    preds, usage = process_cases(client, cases, workers=args.workers)
    elapsed = time.time() - start

    write_predictions(preds, HERE / "predictions_sample.csv")
    metrics = score(preds, gold)
    metrics["runtime_seconds"] = round(elapsed, 1)
    metrics["estimated_cost_usd"] = round(estimate_cost(usage), 4)
    metrics["usage"] = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation_input_tokens": usage.cache_creation_input_tokens,
        "cache_read_input_tokens": usage.cache_read_input_tokens,
    }

    (HERE / "metrics.json").write_text(json.dumps(metrics, indent=2))
    write_diff(preds, gold, metrics, HERE / "diff_sample.md")
    print_report(metrics)
    print(f"\nRuntime: {elapsed:.1f}s   Estimated cost: ${metrics['estimated_cost_usd']}",
          file=sys.stderr)
    print(f"Wrote {HERE/'predictions_sample.csv'}, {HERE/'metrics.json'}, "
          f"and {HERE/'diff_sample.md'}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
