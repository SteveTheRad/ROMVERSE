from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True, slots=True)
class LegalDocument:
    document_id: str
    version: str
    status: str
    text: str
    sha256: str


TERMS_RESOURCE = "TERMS-AND-CONDITIONS-DRAFT.md"
TERMS_DOCUMENT_ID = "romverse-terms-and-conditions"
TERMS_VERSION = "draft-2026-09-04"
TERMS_STATUS = "INTERNAL REVIEW DRAFT • NOT YET EFFECTIVE"


def load_terms_document() -> LegalDocument:
    """Load the packaged bounded Terms draft; this does not record acceptance."""

    text = files("romverse.assets").joinpath(TERMS_RESOURCE).read_text(encoding="utf-8")
    if not 1_000 <= len(text) <= 50_000 or "\x00" in text:
        raise ValueError("Packaged Terms document has an invalid size or encoding")
    required = (
        "# ROMVERSE Terms & Conditions",
        "## 4. High-risk Android operations",
        "## 10. No blanket waiver of legal rights",
        "Australian Consumer Law",
        "not authorise a device-changing operation",
    )
    if any(item not in text for item in required):
        raise ValueError("Packaged Terms document is incomplete")
    return LegalDocument(
        TERMS_DOCUMENT_ID,
        TERMS_VERSION,
        TERMS_STATUS,
        text,
        hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
