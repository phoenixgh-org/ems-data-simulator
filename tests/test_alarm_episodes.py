"""Tests for the DetectedIssue episode derivation (decision prototype).

Verifies that the per-record alarm stream collapses into one DetectedIssue per
contiguous episode (per code), and that the result is structurally valid FHIR.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "fhir" / "transform"))

from alarm_episodes import detected_issues, _episodes_for_report, bundle_with_issues  # noqa: E402


def _rec(abst, alrm=None):
    return {"ABST": abst, "ALRM": alrm}


def test_contiguous_run_is_one_episode():
    recs = [_rec("20240101T000000Z"),
            _rec("20240101T001500Z", "HEAT"),
            _rec("20240101T003000Z", "HEAT"),
            _rec("20240101T004500Z", "HEAT"),
            _rec("20240101T010000Z")]
    eps = _episodes_for_report(recs)
    assert len(eps) == 1
    assert eps[0]["code"] == "HEAT"
    assert eps[0]["count"] == 3
    assert eps[0]["start"] == "20240101T001500Z"
    assert eps[0]["end"] == "20240101T004500Z"


def test_gap_splits_into_two_episodes():
    recs = [_rec("20240101T000000Z", "HEAT"),
            _rec("20240101T001500Z"),            # clears
            _rec("20240101T003000Z", "HEAT")]    # re-fires
    eps = [e for e in _episodes_for_report(recs) if e["code"] == "HEAT"]
    assert len(eps) == 2


def test_multi_code_alrm_tracked_per_code():
    recs = [_rec("20240101T000000Z", "HEAT"),
            _rec("20240101T001500Z", "HEAT DOOR"),
            _rec("20240101T003000Z", "HEAT")]
    eps = {e["code"]: e for e in _episodes_for_report(recs)}
    assert set(eps) == {"HEAT", "DOOR"}
    assert eps["HEAT"]["count"] == 3
    assert eps["DOOR"]["count"] == 1


def test_detected_issue_shape():
    tx = {"meta": {"transferType": "ems"},
          "data": [{"AMFR": "x", "AMOD": "y", "ADOP": "2024-01-01", "APQS": "E003/1",
                    "records": [_rec("20240101T000000Z", "HEAT"),
                                _rec("20240101T001500Z", "HEAT")]}]}
    dis = detected_issues(tx)
    assert len(dis) == 1
    di = dis[0]
    assert di["resourceType"] == "DetectedIssue"
    assert di["code"]["coding"][0]["code"] == "HEAT"
    assert di["severity"] == "high"
    assert di["identifiedPeriod"]["start"] == "2024-01-01T00:00:00Z"
    assert di["identifiedPeriod"]["end"] == "2024-01-01T00:15:00Z"
    assert di["implicated"][0]["reference"].endswith("/Device/appliance-0")


def test_detected_issue_bundle_validates_r4b():
    """Structural R4B validation (skips if fhir.resources absent)."""
    pytest.importorskip("fhir.resources.R4B.bundle")
    from fhir.resources.R4B.bundle import Bundle
    from fhir.resources.R4B.detectedissue import DetectedIssue

    tx = {"meta": {"transferType": "ems"},
          "data": [{"AMFR": "x", "AMOD": "y", "ADOP": "2024-01-01", "APQS": "E003/1",
                    "records": [_rec("20240101T000000Z", "HEAT"),
                                _rec("20240101T001500Z", "HEAT")]}]}
    b = bundle_with_issues(tx)
    Bundle.parse_obj(b)
    for e in b["entry"]:
        if e["resource"]["resourceType"] == "DetectedIssue":
            DetectedIssue.parse_obj(e["resource"])
