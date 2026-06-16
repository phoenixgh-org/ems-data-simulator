"""Derive FHIR DetectedIssue episodes from the per-record EMS alarm stream.

Decision prototype for ccesim-jby.3. The Phase 2 transform already emits each
per-record ALRM/EERR/LERR code as a coded Observation (lossless, 1:1 with the
wire). EMS alarms, however, are *excursion-timer episodes*: a single logical
alarm (e.g. HEAT = TVC>8 C for 10h) stays active across many consecutive records.
In the example data, one HEAT excursion spans 65 records -> 65 near-identical
Observations.

This module collapses those into one **DetectedIssue per episode** (per code),
with an `identifiedPeriod` covering the excursion. DetectedIssue is the
consumer-facing, de-duplicated, alert-oriented representation; the per-record
Observations remain the lossless base. See the decision record in
fhir/decisions/0001-alarm-modeling.md.

Scope note: this derivation is an interoperability-layer concern. Full
integration (wiring into the IG, evidence links to the contributing temperature
Observations, severity taxonomy) is Phase 3 (ccesim-jby.5). This module proves
the chosen model is implementable and R4-valid.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cce_to_fhir import abst_to_instant, CS_ALARMS, RES_BASE  # noqa: E402

# E003 alarm severity. HEAT/FRZE are vaccine-safety excursions (high); DOOR/POWR
# are conditions that lead to excursions if unaddressed (moderate).
SEVERITY = {"HEAT": "high", "FRZE": "high", "DOOR": "moderate", "POWR": "moderate"}


def _episodes_for_report(records: list[dict]) -> list[dict]:
    """Group consecutive records sharing an active alarm code into episodes.

    Returns a list of {code, start, end, count}. ALRM is a space-delimited string
    that may carry several codes at once, so episodes are tracked per code.
    """
    records = sorted(records, key=lambda r: r["ABST"])
    open_eps: dict[str, dict] = {}   # code -> {start, end, count}
    done: list[dict] = []

    for r in records:
        active = set(str(r.get("ALRM") or "").split())
        # extend or open episodes for currently-active codes
        for code in active:
            ep = open_eps.get(code)
            if ep is None:
                open_eps[code] = {"code": code, "start": r["ABST"], "end": r["ABST"], "count": 1}
            else:
                ep["end"] = r["ABST"]
                ep["count"] += 1
        # close episodes whose code is no longer active
        for code in list(open_eps):
            if code not in active:
                done.append(open_eps.pop(code))
    done.extend(open_eps.values())
    return done


def detected_issues(transmission: dict) -> list[dict]:
    """cce-interop EMS transmission -> list of FHIR R4 DetectedIssue dicts."""
    issues: list[dict] = []
    n = 0
    for r_idx, report in enumerate(transmission["data"]):
        device_url = f"{RES_BASE}/Device/appliance-{r_idx}"
        for ep in _episodes_for_report(report["records"]):
            n += 1
            di = {
                "resourceType": "DetectedIssue",
                "id": f"alarm-{r_idx}-{n}",
                "status": "final",
                "code": {"coding": [{"system": CS_ALARMS, "code": ep["code"]}]},
                "identifiedPeriod": {
                    "start": abst_to_instant(ep["start"]),
                    "end": abst_to_instant(ep["end"]),
                },
                "implicated": [{"reference": device_url}],
                "detail": (f"{ep['code']} alarm active across {ep['count']} consecutive "
                           f"records (WHO PQS E003 excursion condition)."),
            }
            sev = SEVERITY.get(ep["code"])
            if sev:
                di["severity"] = sev
            issues.append(di)
    return issues


def bundle_with_issues(transmission: dict) -> dict:
    """A collection Bundle of the implicated appliance Device(s) + DetectedIssues,
    so references resolve for standalone validation."""
    from cce_to_fhir import _device  # local import to avoid cycle at module load

    entries = []
    for r_idx, report in enumerate(transmission["data"]):
        a = report["appliance"] if "appliance" in report else report
        url = f"{RES_BASE}/Device/appliance-{r_idx}"
        dev = _device(url, f"appliance-{r_idx}", a.get("AMFR", "unknown"),
                      a.get("AMOD", "unknown"), a.get("ADOP", ""),
                      a.get("APQS", ""), a.get("ACAT") or "Appliance", None)
        entries.append({"fullUrl": url, "resource": dev})
    for di in detected_issues(transmission):
        entries.append({"fullUrl": f"{RES_BASE}/DetectedIssue/{di['id']}", "resource": di})
    return {"resourceType": "Bundle", "type": "collection", "entry": entries}
