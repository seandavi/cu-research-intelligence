"""Application backend (ADR-0026): the writable overlay + auth tier.

Runs beside the read-only analytics API (ADR-0014/0023). Holds only what users
and the review loop create — identity, sessions, editable profiles, corrections —
in a Postgres overlay separate from the read-only ``serving.duckdb`` and from the
shared cdsci-lake catalog. Everything here is optional: the analytics API runs
unchanged when the ``app`` extra isn't installed or the overlay isn't configured.
"""
