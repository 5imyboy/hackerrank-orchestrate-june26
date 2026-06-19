"""Allowed values and the structured-output model for a claim assessment.

These lists come straight from problem_statement.md ("Allowed values").
Keeping them in one place lets prompt.py advertise them to the model and
normalize.py clamp the model's answer back onto them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- Allowed enum values -----------------------------------------------------
# In Python a "set literal" is written with {...}; membership tests (`x in S`)
# are O(1) like Java's HashSet.contains.

CLAIM_STATUS = {"supported", "contradicted", "not_enough_information"}

ISSUE_TYPE = {
    "dent", "scratch", "crack", "glass_shatter", "broken_part", "missing_part",
    "torn_packaging", "crushed_packaging", "water_damage", "stain", "none", "unknown",
}

SEVERITY = {"none", "low", "medium", "high", "unknown"}

RISK_FLAGS = {
    "none", "blurry_image", "cropped_or_obstructed", "low_light_or_glare",
    "wrong_angle", "wrong_object", "wrong_object_part", "damage_not_visible",
    "claim_mismatch", "possible_manipulation", "non_original_image",
    "text_instruction_present", "user_history_risk", "manual_review_required",
}

# object_part depends on the claim_object. A dict maps each object to its
# allowed parts (dict ~= Java HashMap<String, Set<String>>).
OBJECT_PART = {
    "car": {
        "front_bumper", "rear_bumper", "door", "hood", "windshield", "side_mirror",
        "headlight", "taillight", "fender", "quarter_panel", "body", "unknown",
    },
    "laptop": {
        "screen", "keyboard", "trackpad", "hinge", "lid", "corner", "port",
        "base", "body", "unknown",
    },
    "package": {
        "box", "package_corner", "package_side", "seal", "label", "contents",
        "item", "unknown",
    },
}

# Union of every object_part, used to validate the model output before we know
# (well, we do know) the object. set().union(*dicts.values()) folds all sets.
ALL_OBJECT_PARTS = set().union(*OBJECT_PART.values())

# Final CSV column order required by the contract. A list is ordered (like a
# Java ArrayList); we use it to write the header and each row in order.
OUTPUT_COLUMNS = [
    "user_id", "image_paths", "user_claim", "claim_object",
    "evidence_standard_met", "evidence_standard_met_reason", "risk_flags",
    "issue_type", "object_part", "claim_status", "claim_status_justification",
    "supporting_image_ids", "valid_image", "severity",
]


# --- Structured output model -------------------------------------------------
# Pydantic BaseModel ~= a Java POJO/record with built-in validation. Each field
# below is a typed attribute; Pydantic parses JSON into this class and raises if
# a required field is missing or has the wrong type.
class ClaimAssessment(BaseModel):
    """The 10 fields the model must produce (the other 4 are passthrough input)."""

    evidence_standard_met: bool = Field(
        description="true if the image set is sufficient to evaluate the claim."
    )
    evidence_standard_met_reason: str = Field(
        description="One short sentence justifying the evidence decision."
    )
    risk_flags: list[str] = Field(
        description="List of risk flags from the allowed set, or ['none']."
    )
    issue_type: str = Field(description="Visible issue type from the allowed set.")
    object_part: str = Field(description="Relevant object part for this claim_object.")
    claim_status: str = Field(
        description="supported, contradicted, or not_enough_information."
    )
    claim_status_justification: str = Field(
        description="Concise image-grounded explanation; cite image IDs when helpful."
    )
    supporting_image_ids: list[str] = Field(
        description="Image IDs (filename without extension) supporting the decision; "
        "empty list if none."
    )
    valid_image: bool = Field(
        description="true if the image set is usable for automated review."
    )
    severity: str = Field(description="none, low, medium, high, or unknown.")
