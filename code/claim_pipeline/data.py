"""Load the dataset CSVs and assemble a self-contained "case" per claim.

A "case" bundles everything one model call needs: the claim row, the matching
user-history row, the relevant evidence requirements, and the base64-encoded
images.
"""

from __future__ import annotations

import base64
import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

# Media types the Anthropic API accepts directly. Anything else (e.g. AVIF) is
# converted to PNG before sending.
SUPPORTED_MEDIA = {"image/jpeg", "image/png", "image/gif", "image/webp"}

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


def _sniff_media_type(data: bytes) -> str | None:
    """Detect the real image format from magic bytes (NOT the file extension).

    Dataset files are frequently mislabeled (a .jpg that is actually WebP/AVIF),
    and the API validates the real bytes. Returns a supported media type, or None
    if the format needs conversion (e.g. AVIF/HEIF).
    """
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None  # AVIF/HEIF/unknown -> convert below


def _convert_to_png(data: bytes) -> bytes:
    """Decode any Pillow-readable image (incl. AVIF) and re-encode as PNG."""
    # Imported lazily so the data layer only needs Pillow when a conversion is
    # actually required. `import pillow_avif` registers the AVIF decoder.
    from PIL import Image
    import pillow_avif  # noqa: F401  (side-effect import: registers AVIF)

    with Image.open(io.BytesIO(data)) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()


def _encode_image(rel_path: str, dataset_dir: Path) -> ImageData:
    """Read an image off disk, normalize its format, and base64-encode it."""
    full = dataset_dir / rel_path
    data = full.read_bytes()

    media_type = _sniff_media_type(data)
    if media_type is None:
        # Unsupported on the wire (AVIF etc.): convert to PNG in-memory.
        data = _convert_to_png(data)
        media_type = "image/png"

    b64 = base64.standard_b64encode(data).decode("ascii")
    # filename without extension: Path("img_1.jpg").stem -> "img_1"
    image_id = Path(rel_path).stem
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
