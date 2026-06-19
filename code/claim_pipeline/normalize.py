"""Turn a (Case, ClaimAssessment) into a clean output row.

This is the determinism / safety layer: whatever the model returns, the final
CSV only ever contains allowed enum values, correctly formatted multi-value
fields, and image IDs that actually exist in the claim.
"""

from __future__ import annotations

from . import schema
from .data import Case
from .schema import ClaimAssessment


def _bool_str(value: bool) -> str:
    """Python's True/False -> the lowercase "true"/"false" the contract wants."""
    return "true" if value else "false"


def _clamp(value: str, allowed: set[str], fallback: str) -> str:
    """Return value if it's an allowed enum, else the fallback."""
    v = (value or "").strip()
    return v if v in allowed else fallback


def _clean_risk_flags(flags: list[str]) -> str:
    """Keep only allowed flags, dedupe, drop 'none' if real flags exist."""
    seen: list[str] = []
    for f in flags:
        f = (f or "").strip()
        if f in schema.RISK_FLAGS and f not in seen:
            seen.append(f)  # list keeps insertion order (like LinkedHashSet)
    real = [f for f in seen if f != "none"]
    if real:
        return ";".join(real)
    return "none"


def _clean_supporting_ids(ids: list[str], case: Case) -> str:
    """Keep only IDs that are actually images on this claim; else 'none'."""
    valid_ids = {img.image_id for img in case.images}  # set comprehension
    kept: list[str] = []
    for i in ids:
        i = (i or "").strip()
        if i in valid_ids and i not in kept:
            kept.append(i)
    return ";".join(kept) if kept else "none"


def to_output_row(case: Case, a: ClaimAssessment) -> dict[str, str]:
    """Build the final 14-column row as a dict keyed by OUTPUT_COLUMNS.

    The first four columns are passthrough from the input; the rest are the
    clamped model fields.
    """
    object_parts = schema.OBJECT_PART.get(case.claim_object, schema.ALL_OBJECT_PARTS)

    row = {
        # passthrough input columns, verbatim
        "user_id": case.user_id,
        "image_paths": case.image_paths,
        "user_claim": case.user_claim,
        "claim_object": case.claim_object,
        # model-produced columns, clamped to the contract's allowed values
        "evidence_standard_met": _bool_str(a.evidence_standard_met),
        "evidence_standard_met_reason": a.evidence_standard_met_reason.strip(),
        "risk_flags": _clean_risk_flags(a.risk_flags),
        "issue_type": _clamp(a.issue_type, schema.ISSUE_TYPE, "unknown"),
        "object_part": _clamp(a.object_part, object_parts, "unknown"),
        "claim_status": _clamp(
            a.claim_status, schema.CLAIM_STATUS, "not_enough_information"
        ),
        "claim_status_justification": a.claim_status_justification.strip(),
        "supporting_image_ids": _clean_supporting_ids(a.supporting_image_ids, case),
        "valid_image": _bool_str(a.valid_image),
        "severity": _clamp(a.severity, schema.SEVERITY, "unknown"),
    }
    return row


def error_row(case: Case, message: str) -> dict[str, str]:
    """Fallback row if a claim fails entirely, so output.csv stays complete.

    Marked for manual review rather than silently dropped.
    """
    return {
        "user_id": case.user_id,
        "image_paths": case.image_paths,
        "user_claim": case.user_claim,
        "claim_object": case.claim_object,
        "evidence_standard_met": "false",
        "evidence_standard_met_reason": f"Automated review failed: {message}"[:300],
        "risk_flags": "manual_review_required",
        "issue_type": "unknown",
        "object_part": "unknown",
        "claim_status": "not_enough_information",
        "claim_status_justification": "Processing error; routed to manual review.",
        "supporting_image_ids": "none",
        "valid_image": "false",
        "severity": "unknown",
    }
