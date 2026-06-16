"""Reference transformer: cce-interop-0.8.0 EMS transmission -> FHIR R4 Bundle.

Phase 2 of the FHIR adoption epic (ccesim-jby.4), Option A: a plain Bundle of
Device + Observation resources (minimal profiling).

This Python implementation is the *executable reference* for the StructureMap in
``fhir/input/maps/cce-interop-to-bundle.fml``. The two MUST stay in lockstep: the
FML is the canonical, portable transform; this module is the working executable
today. Its output validates against FHIR R4 (4.0.1) with 0 errors using HL7's own
Java validator (and against R4B via ``fhir.resources``). Making the FML itself
engine-executable and matching its output here is tracked in ccesim-jby.7.

Mapping summary
---------------
meta                      -> Bundle (type=collection); identifier=transferId; timestamp=transferredAt
report.appliance          -> Device (anchor)             ASER/AID, AMFR, AMOD, ADOP, APQS, ACAT
report.emd                -> Device, parent=appliance     ESER/EID, EMFR, EMOD, EDOP, EPQS, EMSV
report.logger             -> Device, parent=emd           LSER/LID, LMFR, LMOD, LDOP, LPQS, LSV
report.location           -> (carried on Devices via property; full Location is Phase 3)
record.<numeric object>   -> Observation (valueQuantity + UCUM); effectiveInstant=ABST; device=emd, subject=appliance
record.MSW                -> Observation (valueBoolean)
record.ALRM (per code)    -> Observation (valueCodeableConcept from PqsE003Alarms)
record.EERR/LERR          -> Observation (valueCodeableConcept from Cce*ErrorCodes)
"""
from __future__ import annotations

import re
from typing import Any

# Canonical base for the CodeSystems authored in Phase 1 (ccesim-jby.2).
# Bundle.entry.fullUrl must be an absolute URI. We use resource-typed URLs under a
# base rather than `urn:uuid:` -- the urn:uuid scheme requires a real lowercase
# UUID (enforced by the HL7 validator), and our ids are deterministic, not UUIDs.
RES_BASE = "https://worldhealthorg.example/fhir/cce"

CS_OBJECTS = "https://worldhealthorg.example/fhir/cce/CodeSystem/pqs-e006-data-objects"
CS_ALARMS = "https://worldhealthorg.example/fhir/cce/CodeSystem/pqs-e003-alarms"
CS_EERR = "https://worldhealthorg.example/fhir/cce/CodeSystem/cce-emd-error-codes"
CS_LERR = "https://worldhealthorg.example/fhir/cce/CodeSystem/cce-logger-error-codes"
UCUM = "http://unitsofmeasure.org"

# UCUM unit per numeric data object. Units follow the authoritative Annex/schema
# definitions (HOLD, BEMD, BLOG in DAYS; SVA/runtime/door in seconds; CMPS in rpm).
UNITS: dict[str, tuple[str, str]] = {
    # temperatures (degree Celsius)
    "TVC": ("Cel", "°C"), "TFRZ": ("Cel", "°C"), "TAMB": ("Cel", "°C"),
    "TCON": ("Cel", "°C"), "TCON2": ("Cel", "°C"),
    "TPCB": ("Cel", "°C"), "TPCB2": ("Cel", "°C"),
    # relative humidity / fan / battery-percent-style
    "HAMB": ("%", "%"), "HCOM": ("%", "%"), "FANS": ("%", "%"),
    # electrical
    "ACCD": ("A", "A"), "DCCD": ("A", "A"), "ACSV": ("V", "V"), "DCSV": ("V", "V"),
    # durations within the interval (seconds)
    "SVA": ("s", "s"), "CMPR": ("s", "s"), "CMPR2": ("s", "s"),
    "DORV": ("s", "s"), "DORF": ("s", "s"), "IDRV": ("s", "s"), "IDRF": ("s", "s"),
    # rotational speed (rpm)
    "CMPS": ("/min", "rpm"), "CMPS2": ("/min", "rpm"),
    # counts
    "DRCV": ("{count}", "openings"), "DRCF": ("{count}", "openings"),
    # autonomy / battery life (days)
    "HOLD": ("d", "d"), "BEMD": ("d", "d"), "BLOG": ("d", "d"),
}

# Human-readable display per object code (for Observation.code.coding.display).
DISPLAY: dict[str, str] = {
    "TVC": "Vaccine compartment temperature", "TFRZ": "Freezer compartment temperature",
    "TAMB": "Ambient temperature", "TCON": "Condenser temperature",
    "TCON2": "Secondary condenser temperature", "TPCB": "Compressor electronic unit temperature",
    "TPCB2": "Secondary compressor electronic unit temperature",
    "HAMB": "Ambient relative humidity", "HCOM": "Compartment relative humidity",
    "FANS": "Fan speed", "ACCD": "AC current drawn", "DCCD": "DC current drawn",
    "ACSV": "AC supply voltage", "DCSV": "DC supply voltage",
    "SVA": "AC supply voltage availability", "CMPR": "Compressor runtime",
    "CMPR2": "Secondary compressor runtime", "DORV": "Vaccine door-open duration",
    "DORF": "Freezer door-open duration", "IDRV": "Instantaneous vaccine door-open",
    "IDRF": "Instantaneous freezer door-open", "CMPS": "Compressor speed",
    "CMPS2": "Secondary compressor speed", "DRCV": "Vaccine door-opening count",
    "DRCF": "Freezer door-opening count", "HOLD": "Holdover autonomy",
    "BEMD": "EMD battery remaining", "BLOG": "Logger battery remaining",
    "MSW": "Main ON/OFF switch", "ALRM": "Alarm condition",
    "EERR": "EMD error codes", "LERR": "Logger error codes",
}

_ABST_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(\.\d+)?Z$")


def abst_to_instant(abst: str) -> str:
    """ISO-basic ABST (``20240103T172228Z``) -> FHIR ``instant`` (``2024-01-03T17:22:28Z``)."""
    m = _ABST_RE.match(abst)
    if not m:
        raise ValueError(f"ABST not in expected basic ISO format: {abst!r}")
    y, mo, d, h, mi, s, frac = m.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}{frac or ''}Z"


def _ref(fullurl: str) -> dict:
    return {"reference": fullurl}


def _device(fullurl: str, did: str, mfr: str, mod: str, dop: str,
            pqs: str, dtype_text: str, parent_url: str | None,
            extra_props: dict[str, str] | None = None) -> dict:
    dev: dict[str, Any] = {
        "resourceType": "Device",
        "id": did,
        "manufacturer": mfr,
        "modelNumber": mod,
        "type": {"text": dtype_text},
    }
    if dop:
        dev["manufactureDate"] = f"{dop}T00:00:00Z" if "T" not in dop else dop
    ids = []
    if did:
        ids.append({"value": did})
    if ids:
        dev["identifier"] = ids
    props = dict(extra_props or {})
    if pqs:
        props["PQS-code"] = pqs
    if props:
        dev["property"] = [
            {"type": {"text": k}, "valueQuantity": None, "valueCode": [{"text": v}]}
            for k, v in props.items()
        ]
        # `property.valueCode` is a CodeableConcept list in R4; drop the null quantity
        for p in dev["property"]:
            p.pop("valueQuantity", None)
    if parent_url:
        dev["parent"] = _ref(parent_url)
    return dev


def _observation(oid: str, obj_code: str, instant: str,
                 device_url: str, subject_url: str, *,
                 value: dict) -> dict:
    obs = {
        "resourceType": "Observation",
        "id": oid,
        "status": "final",
        # `display` is intentionally omitted: it is a denormalization of the
        # CodeSystem's display and the HL7 validator rejects any value that does
        # not match the CodeSystem exactly. Consumers resolve the display from
        # PqsE006DataObjects. (DISPLAY is kept for human-facing tooling/logs.)
        "code": {"coding": [{"system": CS_OBJECTS, "code": obj_code}]},
        "effectiveInstant": instant,
        "device": _ref(device_url),
        "subject": _ref(subject_url),
    }
    obs.update(value)
    return obs


def transform(transmission: dict) -> dict:
    """cce-interop EMS transmission dict -> FHIR R4 Bundle dict."""
    meta = transmission["meta"]
    if meta.get("transferType") != "ems":
        raise ValueError(f"transferType must be 'ems', got {meta.get('transferType')!r}")

    entries: list[dict] = []
    n = 0  # monotonic id counter for stable, deterministic resource ids

    for r_idx, report in enumerate(transmission["data"]):
        # fullUrl must end in /{type}/{id} matching the resource id (HL7 validator
        # enforces this for RESTful-looking URLs).
        appliance_url = f"{RES_BASE}/Device/appliance-{r_idx}"
        emd_url = f"{RES_BASE}/Device/emd-{r_idx}"
        logger_url = f"{RES_BASE}/Device/logger-{r_idx}"

        loc_props = {}
        for k in ("FID", "FNAM", "DNAM", "RNAM"):
            if report.get(k):
                loc_props[k] = str(report[k])
        for k in ("LAT", "LNG", "LACC"):
            if report.get(k) is not None:
                loc_props[k] = str(report[k])

        appliance = _device(appliance_url, f"appliance-{r_idx}",
                            report["AMFR"], report["AMOD"], report["ADOP"],
                            report["APQS"], report.get("ACAT") or "Appliance",
                            None, extra_props=loc_props)
        if report.get("AID"):
            appliance["identifier"].append({"value": report["AID"]})
        emd = _device(emd_url, f"emd-{r_idx}", report["EMFR"], report["EMOD"],
                     report["EDOP"], report["EPQS"], "EMD", appliance_url)
        if report.get("EMSV"):
            emd["version"] = [{"value": report["EMSV"]}]
        logger = _device(logger_url, f"logger-{r_idx}", report["LMFR"],
                        report["LMOD"], report["LDOP"], report["LPQS"],
                        "Logger", emd_url)

        for dev, url in ((appliance, appliance_url), (emd, emd_url), (logger, logger_url)):
            entries.append({"fullUrl": url, "resource": dev})

        for record in report["records"]:
            instant = abst_to_instant(record["ABST"])
            for obj, (ucum, disp_unit) in UNITS.items():
                val = record.get(obj)
                if val is None:
                    continue
                n += 1
                ourl = f"{RES_BASE}/Observation/obs-{n}"
                value = {"valueQuantity": {"value": val, "unit": disp_unit,
                                          "system": UCUM, "code": ucum}}
                entries.append({"fullUrl": ourl, "resource": _observation(
                    f"obs-{n}", obj, instant, emd_url, appliance_url, value=value)})

            # MSW: boolean main switch
            if record.get("MSW") is not None:
                n += 1
                entries.append({"fullUrl": f"{RES_BASE}/Observation/obs-{n}", "resource": _observation(
                    f"obs-{n}", "MSW", instant, emd_url, appliance_url,
                    value={"valueBoolean": bool(record["MSW"])})})

            # coded alarms / errors (space-delimited wire string -> one Observation per code)
            for obj, sys in (("ALRM", CS_ALARMS), ("EERR", CS_EERR), ("LERR", CS_LERR)):
                raw = record.get(obj)
                if not raw:
                    continue
                for code in str(raw).split():
                    n += 1
                    entries.append({"fullUrl": f"{RES_BASE}/Observation/obs-{n}", "resource": _observation(
                        f"obs-{n}", obj, instant, emd_url, appliance_url,
                        value={"valueCodeableConcept": {
                            "coding": [{"system": sys, "code": code}]}})})

    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "identifier": {"value": meta["transferId"]},
        "entry": entries,
    }
    ts = meta.get("transferredAt")
    if ts:
        # transferredAt may be a datetime (from the simulator) or a string
        bundle["timestamp"] = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    return bundle
