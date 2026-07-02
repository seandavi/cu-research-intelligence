"""Authorization roles for the application backend (ADR-0026).

Roles are rows in the overlay (``user_role``), seeded from the roster and admin
assignment. An authenticated user with no role row is a *viewer* — the public
analytics only. Role gating is what turns "logged in" into the different
experiences the platform's audiences need.
"""

from __future__ import annotations

MEMBER = "member"  # edit own profile; claim/disclaim + self-score own publications
LIAISON = "liaison"  # first-line catchment review for their program (ADR-0027)
PROGRAM_LEADER = "program_leader"  # confirm reviews for their program
LIBRARIAN = "librarian"  # curate catchment search terms / candidate lists
LEADERSHIP = "leadership"  # cross-program views, exports
ADMIN = "admin"  # role/identity administration, everything

ROLES: frozenset[str] = frozenset(
    {MEMBER, LIAISON, PROGRAM_LEADER, LIBRARIAN, LEADERSHIP, ADMIN}
)
