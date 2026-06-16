# CCE / EMS FHIR — Logical Models & Terminology (Phase 1)

FHIR-native expression of the WHO PQS E006 EMS / CCE data structure, derived from
the `cce-interop-0.8.0` delivery schema. This is **Phase 1** of the FHIR adoption
epic (beads `ccesim-jby`); see the working-draft assessment at
[`../docs/fhir-ems-assessment.md`](../docs/fhir-ems-assessment.md) for the full rationale.

> Status: **draft / experimental**. Canonical URLs use a placeholder host
> (`worldhealthorg.example`) pending a governance decision on namespace ownership
> (beads `ccesim-jby.2`).

## What's here

| File | Contents |
|------|----------|
| `input/fsh/logical-models.fsh` | `CceTransmission` → `CceEmsReport` → `CceEmsRecord` logical models (`ccesim-jby.1`) |
| `input/fsh/codesystems.fsh` | `PqsE006DataObjects` (71 object codes), `PqsE003Alarms`, `CceEmdErrorCodes`, `CceLoggerErrorCodes` (`ccesim-jby.2`) |
| `input/fsh/valuesets.fsh` | ValueSets backing the logical-model field bindings |
| `sushi-config.yaml` | SUSHI build config (`FSHOnly` — no full IG yet) |
| `input/maps/cce-interop-to-bundle.fml` | **Phase 2** StructureMap: cce-interop EMS → FHIR Bundle (`ccesim-jby.4`) |
| `transform/cce_to_fhir.py` | Executable reference transformer (lockstep with the FML) |
| `transform/run_phase2_poc.py` | PoC driver: generate → transform → validate |
| `examples/` | Generated `ems-transmission.json` + `ems-bundle.json` (gitignored — regenerate via the driver) |

## Phase 2 — transform PoC (Option A)

Maps a cce-interop EMS transmission to a plain FHIR R4 **Bundle** of `Device` +
`Observation` resources:

- transmission `meta` → `Bundle` (`identifier`=transferId, `timestamp`=transferredAt)
- appliance / EMD / logger → `Device` hierarchy via `Device.parent`
- each numeric record object → `Observation` with `valueQuantity` + UCUM units and
  `effectiveInstant` (ABST normalized from ISO-basic to ISO-extended)
- `ALRM`/`EERR`/`LERR` → coded `Observation` (`valueCodeableConcept`); `MSW` → `valueBoolean`

```bash
pip install "fhir.resources>=7.0.0"        # optional; only needed for validation
python fhir/transform/run_phase2_poc.py    # writes + validates examples/
python -m pytest tests/test_fhir_transform.py
```

`fhir.resources` is an optional, FHIR-only dependency (not required by the core
simulator). The transform test skips cleanly when it is not installed.

> **Engine caveat.** The `.fml` is the canonical, portable transform but is **not
> executed here** — Matchbox / the HL7 validator `-transform` are Java-only and no
> JVM is available in this environment. The Python transformer is the executable
> proof (its output validates against FHIR R4B via `fhir.resources`). Running the
> `.fml` itself through a real engine in a Java-enabled CI is tracked as
> `ccesim-jby.7`; the two implementations must stay in lockstep.

## Design notes

- **Cardinalities** follow the schema's `required` lists. `ABST` and `ADOP`/`EDOP`/etc.
  are typed as `instant`/`date` (the wire uses ISO-basic strings — normalized by the
  Phase 2 StructureMap).
- **Grouping**: the flat wire schema (e.g. `AMFR` at report root) is grouped here into
  `appliance` / `emd` / `logger` / `compressorUnit` / `location` BackboneElements for
  clarity. Flattening is a transform concern (Phase 2, `ccesim-jby.4`).
- **Corrected units** (vs. early draft): `HOLD` and `BEMD`/`BLOG` are in **days**,
  `SVA` in seconds, `CMPS` in rpm — per the authoritative Annex/schema definitions.
- **Alarms/errors**: `ALRM`/`EERR`/`LERR` modeled as `0..*` coded (wire format is a
  space-delimited string; absence = no alarm). Whether downstream alarms become
  `Observation` vs `DetectedIssue` is decision `ccesim-jby.3`.

## Build

Requires Node. SUSHI is run via `npx` (no global install needed):

```bash
cd fhir
npx fsh-sushi@latest .
# -> fsh-generated/resources/*.json  (StructureDefinitions, CodeSystems, ValueSets)
```

`fsh-generated/` is build output and is gitignored. A full IG build (HTML, narrative,
ConceptMaps to LOINC/UCUM) is scoped for Phase 3 (`ccesim-jby.5`).
