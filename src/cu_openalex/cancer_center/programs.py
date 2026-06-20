"""Program taxonomy normalization and publication-type policy.

The roster's free-text ``PrimaryProgram`` mixes the center's current research
programs with legacy labels, near-duplicates, and non-program buckets. Comparing
them as peers (in a heatmap or bar chart) is misleading — a defunct 3-member
"program" should not sit next to a 285-member one. This module centralizes:

* **Program aliases** — fold near-duplicate labels into one canonical program.
* **Non-programs** — buckets that are not scientific programs at all.
* **Publication types** — which OpenAlex ``type`` values count as a publication.

These are policy choices the cancer center controls; defaults are conservative
and documented. Anything flagged here is auditable rather than silently applied.
"""

from __future__ import annotations

# Near-duplicate program labels folded into a canonical name. The
# "Molecular Oncology" → "Molecular & Cellular Oncology" fold is a *candidate*
# reconciliation flagged by review; confirm against the center's official
# program list before relying on it. Set to {} to disable all folding.
PROGRAM_ALIASES: dict[str, str] = {
    "Molecular Oncology": "Molecular & Cellular Oncology",
}

# Labels that are not real research programs (excluded from program comparisons).
NON_PROGRAMS: frozenset[str] = frozenset(
    {"", "Unknown/ Unaffiliated/ Emeritus", "Unknown/Unaffiliated/Emeritus"}
)

# The center's *current* research programs. The remaining roster labels (Cancer
# Cell Biology, Lung/Head & Neck, Hormone-Related, Immunology, Carcinogenesis,
# Hematologic Malignancies, Cancer Genetics, …) are deprecated; program-level
# comparisons default to these four to avoid intermixing retired structures.
CURRENT_PROGRAMS: tuple[str, ...] = (
    "Cancer Prevention & Control",
    "Developmental Therapeutics",
    "Molecular & Cellular Oncology",
    "Tumor-Host Interactions",
)


def current_programs_sql() -> str:
    """SQL list literal of current programs for an ``IN (...)`` filter."""
    return "(" + ", ".join("'" + p.replace("'", "''") + "'" for p in CURRENT_PROGRAMS) + ")"


# OpenAlex work ``type`` values that count as a peer-reviewed publication for
# CCSG reporting. Excludes preprint, supplementary-materials, dataset, paratext,
# peer-review, etc. A 2023 OpenAlex bulk-index event injected thousands of
# AACR supplementary files mislabeled as preprints — filtering by type removes
# that artifact (see ADR-0013).
PUBLICATION_TYPES: frozenset[str] = frozenset({"article", "review"})

# Plausible publication-year bounds (drops dirty values like 1620 / 2027).
MIN_VALID_YEAR = 1950
MAX_VALID_YEAR = 2026


def canonical_program(name: str | None) -> str | None:
    """Map a raw program label to its canonical form (alias-folded)."""
    if name is None:
        return None
    return PROGRAM_ALIASES.get(name, name)


def is_real_program(name: str | None) -> bool:
    """True if ``name`` is a real research program (not a non-program bucket)."""
    return name is not None and name not in NON_PROGRAMS


def publication_types_sql() -> str:
    """SQL list literal of publication types, e.g. ``('article', 'review')``."""
    return "(" + ", ".join(f"'{t}'" for t in sorted(PUBLICATION_TYPES)) + ")"
