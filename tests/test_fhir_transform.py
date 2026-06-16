"""Tests for the Phase 2 FHIR transform (ccesim-jby.4).

Covers the cce-interop EMS -> FHIR R4 Bundle reference transformer:
ABST normalization, structural validity against FHIR R4B models, UCUM units,
effectiveInstant, the Device.parent hierarchy, and the coded-alarm path.

Skips cleanly if `fhir.resources` is not installed (it is an optional, FHIR-only
dependency, not required by the core simulator).
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "fhir" / "transform"))

from cce_to_fhir import transform, abst_to_instant, UNITS, UCUM  # noqa: E402

from utils.device import MonitoringDeviceConfig, BaseRtmDevice  # noqa: E402
from utils.generator import transfer_metadata  # noqa: E402
from utils.simulator.config import FaultType  # noqa: E402

fhir_r4b = pytest.importorskip("fhir.resources.R4B.bundle")
from fhir.resources.R4B.bundle import Bundle  # noqa: E402
from fhir.resources.R4B.device import Device  # noqa: E402
from fhir.resources.R4B.observation import Observation  # noqa: E402


@pytest.mark.parametrize("abst,expected", [
    ("20240103T172228Z", "2024-01-03T17:22:28Z"),
    ("20200115T040554Z", "2020-01-15T04:05:54Z"),
    ("20240103T172228.5Z", "2024-01-03T17:22:28.5Z"),
])
def test_abst_to_instant(abst, expected):
    assert abst_to_instant(abst) == expected


def test_abst_rejects_non_basic_format():
    with pytest.raises(ValueError):
        abst_to_instant("2024-01-03T17:22:28Z")


@pytest.fixture(scope="module")
def ems_bundle():
    """A real simulator EMS transmission -> Bundle.

    Compressor failure at +2h with the icebank intact; the 9-day horizon lets the
    ~9-day holdover exhaust so a HEAT alarm (TVC>8 C for 10h) arises naturally --
    no thermal-config hacks. ~4s to generate + transform.
    """
    horizon_s = 9 * 24 * 3600
    cfg = MonitoringDeviceConfig(type="ems", upload_interval=horizon_s, sample_interval=900)
    device = BaseRtmDevice(cfg)
    device.sim_config.fault.fault_type = FaultType.COMPRESSOR_FAILURE
    device.sim_config.fault.fault_start_offset_s = 2 * 3600

    start = dt.datetime(2024, 6, 15, 0, 0, 0)
    report = device.create_report(report_time=start + dt.timedelta(seconds=horizon_s))
    tx = {"meta": transfer_metadata(type="ems"),
          "data": [report.model_dump(mode="json", exclude_unset=True)]}
    return transform(tx)


def test_transform_requires_ems_transfer_type():
    with pytest.raises(ValueError):
        transform({"meta": {"transferType": "rtmd", "transferId": "x"}, "data": []})


def test_bundle_validates_against_fhir_r4b(ems_bundle):
    Bundle.parse_obj(ems_bundle)
    for entry in ems_bundle["entry"]:
        res = entry["resource"]
        if res["resourceType"] == "Device":
            Device.parse_obj(res)
        elif res["resourceType"] == "Observation":
            Observation.parse_obj(res)


def test_quantity_observations_carry_ucum(ems_bundle):
    q = [e["resource"] for e in ems_bundle["entry"]
         if e["resource"]["resourceType"] == "Observation" and "valueQuantity" in e["resource"]]
    assert q, "expected at least one quantity Observation"
    for o in q:
        assert o["valueQuantity"]["system"] == UCUM
        assert o["valueQuantity"]["code"] in {u[0] for u in UNITS.values()}


def test_observations_have_effective_instant(ems_bundle):
    obs = [e["resource"] for e in ems_bundle["entry"]
           if e["resource"]["resourceType"] == "Observation"]
    assert obs
    for o in obs:
        assert "effectiveInstant" in o and "T" in o["effectiveInstant"] and o["effectiveInstant"].endswith("Z")


def test_device_parent_hierarchy(ems_bundle):
    devs = {d["type"]["text"]: d for d in
            (e["resource"] for e in ems_bundle["entry"] if e["resource"]["resourceType"] == "Device")}
    assert "parent" not in devs["Appliance"]
    assert devs["EMD"]["parent"]["reference"].endswith("device-appliance-0")
    assert devs["Logger"]["parent"]["reference"].endswith("device-emd-0")


def test_coded_alarm_observations_present(ems_bundle):
    alarms = [e["resource"] for e in ems_bundle["entry"]
              if e["resource"]["resourceType"] == "Observation"
              and any(c.get("system", "").endswith("pqs-e003-alarms")
                      for c in e["resource"].get("valueCodeableConcept", {}).get("coding", []))]
    assert alarms, "injected compressor failure should yield HEAT alarm Observations"
    assert any(c["code"] == "HEAT" for o in alarms for c in o["valueCodeableConcept"]["coding"])
