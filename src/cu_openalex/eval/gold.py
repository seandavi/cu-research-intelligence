"""Starter gold set for the NL->SQL content eval (docs/eval/05).

Small, curated, and grows over time; the human-verified subset becomes the
calibration set. Includes **negative controls** — questions the data cannot
answer — to test calibrated trust (the system should refuse/flag, not hallucinate).
`expect_tables` lists tables a valid answer's SQL should touch (schema-validity).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoldItem:
    id: str
    question: str
    answerable: bool
    expect_tables: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


GOLD: tuple[GoldItem, ...] = (
    GoldItem(
        "pubs_per_year",
        "How many publications are there per year?",
        True,
        ("works",),
    ),
    GoldItem(
        "members_per_program",
        "How many members are in each program?",
        True,
        ("members",),
    ),
    GoldItem(
        "top_journals",
        "What are the top journals by publication count?",
        True,
        ("works",),
    ),
    GoldItem(
        "inter_program_share",
        "What fraction of publications are inter-programmatic?",
        True,
        ("works",),
    ),
    GoldItem(
        "grants_by_program",
        "Which program has the most NIH grant funding?",
        True,
        ("member_grants",),
    ),
    # --- negative controls: the data cannot answer these ---
    GoldItem(
        "patient_survival",
        "What is the 5-year patient survival rate for lung cancer at our center?",
        False,
        note="No clinical-outcomes data exists; must refuse, not fabricate.",
    ),
    GoldItem(
        "weather",
        "What is the weather in Denver today?",
        False,
        note="Out of scope; must refuse.",
    ),
)
