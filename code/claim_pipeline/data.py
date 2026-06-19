"""Load the dataset CSVs and assemble a self-contained "case" per claim.

A "case" bundles everything one model call needs: the claim row, the matching
user-history row, the relevant evidence requirements, and the base64-encoded
images.
"""

from __future__ import annotations

import base64
import csv
import os
from dataclasses import dataclass, field
from pathlib import Path

# Project root = two levels up from this file (.../code/claim_pipeline/data.py
# -> .../code -> .../<repo>). Path(__file__) is like Java's
# new File(getClass()...); .parents[i] walks up the directory tree.
REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"  # the "/" operator on Path joins segments


@dataclass
class ImageData:
    """One image: its ID (filename without extension) and base64 bytes."""
    image_id: str
    media_type: str
    b64: str
    path: str  # original relative path, for error messages


@dataclass
class Case:
    """Everything needed to assess a single claim."""
    user_id: str
    image_paths: str          # raw CSV value (semicolon-separated), kept verbatim
    user_claim: str
    claim_object: str
    images: list[ImageData] = field(default_factory=list)
    history: dict[str, str] = field(default_factory=dict)       # user_history row
    requirements: list[str] = field(default_factory=list)       # min-evidence texts


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV into a list of dict rows (column name -> value).

    csv.DictReader yields one dict per row keyed by the header, much like
    iterating a List<Map<String,String>> in Java.
    """
    with path.open(newline="", encoding="utf-8") as f:  # `with` ~= try-with-resources
        return list(csv.DictReader(f))


def load_user_history(dataset_dir: Path = DATASET_DIR) -> dict[str, dict[str, str]]:
    """Return {user_id: history_row}. O(1) lookup per claim (~= HashMap)."""
    rows = _read_csv(dataset_dir / "user_history.csv")
    return {row["user_id"]: row for row in rows}  # dict comprehension


def load_requirements(dataset_dir: Path = DATASET_DIR) -> list[dict[str, str]]:
    """Return all evidence-requirement rows (only 11; we filter per claim)."""
    return _read_csv(dataset_dir / "evidence_requirements.csv")


def requirements_for(
    claim_object: str, all_reqs: list[dict[str, str]]
) -> list[str]:
    """Minimum-evidence texts that apply to this object (object rows + 'all')."""
    # List comprehension ~= stream().filter(...).map(...).collect(toList()).
    return [
        r["minimum_image_evidence"]
        for r in all_reqs
        if r["claim_object"] in (claim_object, "all")
    ]


def _encode_image(rel_path: str, dataset_dir: Path) -> ImageData:
    """Read an image off disk and base64-encode it for the API."""
    full = dataset_dir / rel_path
    data = full.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")
    # filename without extension: Path("img_1.jpg").stem -> "img_1"
    image_id = Path(rel_path).stem
    ext = Path(rel_path).suffix.lower()
    media_type = "image/png" if ext == ".png" else "image/jpeg"
    return ImageData(image_id=image_id, media_type=media_type, b64=b64, path=rel_path)


def build_cases(
    claims_csv: Path,
    dataset_dir: Path = DATASET_DIR,
) -> list[Case]:
    """Turn a claims CSV into fully-hydrated Case objects."""
    history = load_user_history(dataset_dir)
    all_reqs = load_requirements(dataset_dir)
    cases: list[Case] = []

    for row in _read_csv(claims_csv):
        # Split "a.jpg;b.jpg" into individual paths; strip() trims whitespace,
        # the `if p.strip()` guard drops empty fragments.
        paths = [p.strip() for p in row["image_paths"].split(";") if p.strip()]
        images = [_encode_image(p, dataset_dir) for p in paths]

        case = Case(
            user_id=row["user_id"],
            image_paths=row["image_paths"],
            user_claim=row["user_claim"],
            claim_object=row["claim_object"],
            images=images,
            history=history.get(row["user_id"], {}),  # .get() returns {} if absent
            requirements=requirements_for(row["claim_object"], all_reqs),
        )
        cases.append(case)

    return cases
