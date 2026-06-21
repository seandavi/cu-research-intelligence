"""Streamlit dashboard for the cancer-center research-intelligence subsection.

Run with::

    uv run --extra dashboard streamlit run \\
        src/cu_openalex/cancer_center/dashboard/Home.py

Pages live under ``pages/`` (auto-discovered by Streamlit). Shared helpers
(``shared.py``, ``charts.py``) sit next to ``Home.py`` and are imported as
``cu_openalex.cancer_center.dashboard.<module>``.
"""

from __future__ import annotations
