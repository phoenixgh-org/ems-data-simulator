"""Transform PoC driver: generate -> transform -> validate.

1. Generate a real cce-interop EMS transmission from the simulator (incl. a fault
   so alarms/errors exercise the coded-Observation path).
2. Transform it to a FHIR R4 Bundle via the reference transformer.
3. Validate every resource with `fhir.resources` (pure-Python FHIR R4 models).

Run from repo root:  python fhir/transform/run_phase2_poc.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
# Import the transformer by its directory (NOT as `fhir.transform...`, which would
# collide with the installed `fhir.resources` namespace package).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ccesim.device import MonitoringDeviceConfig, BaseRtmDevice  # noqa: E402
from ccesim.generator import transfer_metadata  # noqa: E402
from ccesim.simulator.config import FaultType  # noqa: E402
from cce_to_fhir import transform  # noqa: E402

# Validate against R4B models (the closest pure-Python release to the IG's R4
# target, 4.0.1). Device/Observation shapes used here are identical across R4/R4B;
# the library's bare `fhir.resources` would validate against R5, where Device.type
# is a list and property uses value[x] — not our target.
from fhir.resources.R4B.bundle import Bundle  # noqa: E402
from fhir.resources.R4B.device import Device  # noqa: E402
from fhir.resources.R4B.observation import Observation  # noqa: E402


def build_transmission() -> dict:
    # Realistic holdover-exhaustion scenario: a compressor failure at +2h with the
    # icebank INTACT (default ~8.5 MJ, ~9 days of holdover autonomy). TVC stays
    # near setpoint while the ice reserve discharges; once it exhausts (~day 7-8),
    # TVC rises to ambient and the HEAT alarm (TVC>8 C for 10h) fires naturally.
    # The 9-day horizon is long enough to capture that full arc -- which is why a
    # short run shows no alarm: the holdover hasn't run out yet, not a defect.
    horizon_s = 9 * 24 * 3600
    cfg = MonitoringDeviceConfig(type="ems", upload_interval=horizon_s, sample_interval=900)
    device = BaseRtmDevice(cfg)
    device.sim_config.fault.fault_type = FaultType.COMPRESSOR_FAILURE
    device.sim_config.fault.fault_start_offset_s = 2 * 3600

    start = dt.datetime(2024, 6, 15, 0, 0, 0)
    report = device.create_report(report_time=start + dt.timedelta(seconds=horizon_s))

    meta = transfer_metadata(type="ems")
    tx = {"meta": meta, "data": [report.model_dump(mode="json", exclude_unset=True)]}
    return tx


def validate_bundle(bundle: dict) -> dict:
    counts = {"Device": 0, "Observation": 0, "other": 0}
    Bundle.parse_obj(bundle)  # validates the Bundle + structural envelope
    for entry in bundle["entry"]:
        res = entry["resource"]
        rt = res["resourceType"]
        if rt == "Device":
            Device.parse_obj(res)
            counts["Device"] += 1
        elif rt == "Observation":
            Observation.parse_obj(res)
            counts["Observation"] += 1
        else:
            counts["other"] += 1
    return counts


def assert_acceptance(bundle: dict) -> list[str]:
    """Check the acceptance criteria for the transform PoC."""
    checks = []
    obs = [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation"]
    devs = [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Device"]

    # UCUM units on quantity observations
    q = [o for o in obs if "valueQuantity" in o]
    ucum_ok = all(o["valueQuantity"].get("system") == "http://unitsofmeasure.org" for o in q)
    checks.append((f"{len(q)} quantity Observations all carry UCUM units", ucum_ok))

    # effectiveInstant present & ISO-extended
    inst_ok = all("effectiveInstant" in o and "T" in o["effectiveInstant"] for o in obs)
    sample = obs[0]["effectiveInstant"] if obs else "—"
    checks.append((f"all Observations have effectiveInstant (e.g. {sample})", inst_ok))

    # Device hierarchy via Device.parent
    by_type = {d["type"]["text"]: d for d in devs[:3]}
    parent_ok = ("parent" in by_type.get("EMD", {}) and "parent" in by_type.get("Logger", {})
                 and "parent" not in by_type.get("Appliance", {}))
    checks.append(("Device hierarchy: appliance<-emd<-logger via Device.parent", parent_ok))

    # coded alarms present (fault was injected)
    alarms = [o for o in obs if any(c.get("system", "").endswith("pqs-e003-alarms")
              for c in o.get("valueCodeableConcept", {}).get("coding", []))]
    checks.append((f"{len(alarms)} coded alarm Observations emitted (fault injected)", len(alarms) > 0))

    return checks


def main() -> int:
    tx = build_transmission()
    bundle = transform(tx)

    out_dir = REPO / "fhir" / "examples"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ems-transmission.json").write_text(json.dumps(tx, indent=2, default=str))
    (out_dir / "ems-bundle.json").write_text(json.dumps(bundle, indent=2))

    counts = validate_bundle(bundle)
    print(f"Transformed transmission -> Bundle: "
          f"{counts['Device']} Devices, {counts['Observation']} Observations "
          f"({counts['other']} other). All validated against FHIR R4 (fhir.resources).")

    print("\nAcceptance checks:")
    ok = True
    for label, passed in assert_acceptance(bundle):
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed

    print(f"\nWrote fhir/examples/ems-transmission.json and fhir/examples/ems-bundle.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
