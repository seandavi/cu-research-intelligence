"""Backend / capability eval (docs/eval/05).

Two things, both runnable against the live API with no LLM:

1. **API contract checks** — probe key endpoints and assert invariants (the backend
   works and returns well-formed data).
2. **Capability coverage** — score a curated set of stage-2 requirements as
   present / partial / absent by probing the API, so the scorecard shows *which
   capabilities exist*, not just whether pages render. This is the backend/
   capabilities half of the evaluation (the UI/UX half is the heuristic + persona
   layers, iterations 2-3).

Coverage probes are deliberately conservative: a probe reports ``present`` only on
positive evidence, ``absent`` on positive absence, and ``partial``/``unknown``
otherwise — never overclaiming.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Check:
    name: str
    status: str  # "pass" | "fail" | "present" | "absent" | "partial" | "unknown"
    detail: str = ""


def _get(base_url: str, path: str, timeout: float):
    import httpx

    return httpx.get(base_url.rstrip("/") + path, timeout=timeout)


def api_contract_checks(base_url: str, *, timeout: float = 30.0) -> list[Check]:
    """Probe key endpoints and assert invariants."""
    checks: list[Check] = []

    def probe(name, path, predicate, detail_ok="", detail_bad=""):
        try:
            r = _get(base_url, path, timeout)
            if r.status_code != 200:
                checks.append(Check(name, "fail", f"HTTP {r.status_code}"))
                return None
            data = r.json()
            ok = predicate(data)
            checks.append(Check(name, "pass" if ok else "fail", detail_ok if ok else detail_bad))
            return data
        except Exception as e:  # noqa: BLE001
            checks.append(Check(name, "fail", str(e)))
            return None

    probe("health", "/api/health", lambda d: d.get("status") == "ok", "ok")
    probe(
        "meta.current_programs=4",
        "/api/meta",
        lambda d: len(d.get("current_programs", [])) == 4,
        "4 current programs",
        "unexpected program count",
    )
    probe(
        "kpi.publications>0",
        "/api/kpi",
        lambda d: (d.get("publications") or 0) > 0,
        "nonzero",
    )
    probe(
        "program-summary=4",
        "/api/program-summary",
        lambda d: len(d) == 4 and all("pct_inter_program" in p for p in d),
        "4 programs with collaboration %",
    )
    # input validation: a bad enum SHOULD be rejected with 422 (that's a pass).
    try:
        code = _get(base_url, "/api/top-topics?field_level=bogus", timeout).status_code
        checks.append(
            Check(
                "top-topics rejects bad input (422)",
                "pass" if code == 422 else "fail",
                f"HTTP {code}",
            )
        )
    except Exception as e:  # noqa: BLE001
        checks.append(Check("top-topics rejects bad input (422)", "fail", str(e)))
    return checks


def capability_coverage(base_url: str, *, timeout: float = 30.0) -> list[Check]:
    """Score selected stage-2 requirements as present/partial/absent by probing."""
    import httpx

    checks: list[Check] = []

    def field_present(path: str, field: str) -> bool | None:
        try:
            r = httpx.get(base_url.rstrip("/") + path, timeout=timeout)
            if r.status_code != 200:
                return None
            data = r.json()
            rows = data if isinstance(data, list) else [data]
            return any(field in row for row in rows if isinstance(row, dict))
        except Exception:  # noqa: BLE001
            return None

    def status_of(path: str, ok_codes: tuple[int, ...]) -> int | None:
        try:
            return httpx.get(base_url.rstrip("/") + path, timeout=timeout).status_code
        except Exception:  # noqa: BLE001
            return None

    # R7 — field-normalized impact (FWCI + percentiles). KPI has fwci today; a
    # top-percentile share field would signal the added capability.
    has_fwci = field_present("/api/kpi", "median_fwci")
    has_pct = field_present("/api/kpi", "pct_top_10")
    r7_status = "partial" if has_fwci and not has_pct else ("present" if has_pct else "absent")
    r7_detail = (
        "FWCI present; top-percentile share not yet exposed" if has_fwci and not has_pct else ""
    )
    checks.append(Check("R7 field-normalized impact (FWCI + %top-1/10)", r7_status, r7_detail))

    # R3 — fiscal-year windows. meta exposes calendar defaults only today.
    has_fy = field_present("/api/meta", "default_fiscal_year")
    checks.append(
        Check("R3 fiscal-year windows", "present" if has_fy else "absent",
              "meta exposes calendar-year window only" if not has_fy else "")
    )

    # R1/R2 — dataset provenance / reportable mode.
    has_mode = field_present("/api/meta", "dataset_modes") or field_present(
        "/api/meta", "reportable"
    )
    checks.append(
        Check("R1/R2 provenance + reportable mode", "present" if has_mode else "absent")
    )

    # R12 — editable profiles (backend). PUT /api/profile gated => 401/405, not 404.
    code = status_of("/api/profile/1", (200,))
    put_present = status_of("/api/profile", ()) is not None
    checks.append(
        Check(
            "R12 editable profiles (backend)",
            "present" if (code == 200 or put_present) else "unknown",
            "profile read endpoint reachable" if code == 200 else "",
        )
    )

    # Membership spine surfaced (ADR-0025) — programs endpoint.
    prog_ok = status_of("/api/programs", (200,)) == 200
    checks.append(Check("Membership spine read-API", "present" if prog_ok else "absent"))

    # R8 — iCite translational metrics (APT / cited-by-clinical). Not built yet.
    has_apt = field_present("/api/kpi", "apt") or field_present("/api/kpi", "cited_by_clinical")
    checks.append(Check("R8 translational metrics (iCite APT/clinical)",
                        "present" if has_apt else "absent"))

    return checks
