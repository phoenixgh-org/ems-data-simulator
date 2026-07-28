# CCE / EMS FHIR — Logical Models & Terminology

FHIR-native expression of the WHO PQS E006 EMS / CCE data structure, derived from
the `cce-interop-0.8.1` delivery schema.

> Status: **draft / experimental**, and not endorsed by or affiliated with WHO or
> HL7. Canonical URLs use a placeholder host (`worldhealthorg.example`) precisely
> *because* namespace ownership is an open governance question — do not treat
> those URLs as resolvable or authoritative, and do not publish artifacts built
> from them under that namespace.

## Why this exists

The CCE Data Delivery schema (`cce-interop`) is a plain JSON Schema. It says what a
conformant transmission looks like on the wire, but it carries no terminology
bindings and no relationship to the health-information standards that national
systems already run on. Countries receiving this data increasingly have a FHIR-based
health information exchange; "how does vaccine-fridge telemetry enter that
exchange?" is a question the delivery schema alone cannot answer.

Structurally the fit is good. An EMS payload is classic IoT device telemetry: a
hierarchy of physical devices (appliance → EMD → logger → compressor unit) at a
location, emitting a time series of quantitative measurements plus alarm and error
states. FHIR has mature resources for exactly that shape — `Device`, `DeviceMetric`,
`Observation`, `Location`, `Organization`, `Bundle`.

The hard part is semantic, not structural: **there is no published terminology for
the ~70 four-letter PQS data-object codes or the E003 alarm codes**, and several EMS
objects (`HOLD` holdover autonomy, `SVA` supply-voltage availability) have no
off-the-shelf LOINC or SNOMED equivalent. They have to be authored. That is most of
the work here.

## Approach

Three physical mappings are viable, in increasing order of FHIR-idiomatic-ness and
effort:

- **Option A — Bundle of Observations (pragmatic).** Each transmission becomes a
  `Bundle`; each measurement an `Observation` referencing a `Device`. Minimal
  profiling, local codes where LOINC has no equivalent. Fast to stand up and
  immediately consumable by any FHIR server, but weak semantics and no formal
  contract for consumers.
- **Option B — Profiled resources + Implementation Guide (the target).** Authored
  profiles for `Observation`/`Device`/`Location`, a PQS CodeSystem, and ConceptMaps
  to LOINC/UCUM. A strong, sharable contract that validates with the standard FHIR
  validator and composes with national HIE expectations — at the cost of authoring
  terminology, profiles, and maps up front.
- **Option C — `DeviceMetric` streaming (IEEE 11073 aligned).** The most
  device-native model, with built-in calibration and measurement-period semantics.
  Rejected as the primary mapping because `DeviceMetric` is poorly supported by
  national HIE tooling and heavy for consumers who only want temperatures.

**What is implemented here: Option A, with Option B as the target.** Option A is the
interim deliverable that exercises the validator and a real FHIR server end-to-end
and proves the mapping is sound; Option B is where the sharable contract lands. The
intent is to borrow `DeviceMetric` from Option C later, only for the metrics whose
sampling/averaging semantics genuinely need it.

### Why a Logical Model came first

Before committing to any physical mapping, the structure is expressed as a FHIR
**Logical Model** — a `StructureDefinition` with `kind = logical`, which describes an
arbitrary data structure using FHIR's own modeling machinery without that structure
having to *be* a FHIR resource. This buys four things:

1. One canonical, machine-readable definition of the EMS data dictionary, directly
   traceable to `E006/DS01` and `cce-interop`.
2. Terminology binding at the field level, without having to choose a resource yet.
3. A stable source/target for `StructureMap`, so the transform is declarative and
   testable — and the simulator's output is the natural test fixture.
4. Insulation from the mapping debate: whether `ALRM` ends up an `Observation` or a
   `DetectedIssue` is a *mapping* decision, and the Logical Model is unaffected either
   way.

The Logical Model does **not** replace the JSON Schema. It is a parallel, FHIR-native
expression of the same model that unlocks FHIR tooling, validation, and terminology
services.

## What's here

| File | Contents |
|------|----------|
| `input/fsh/logical-models.fsh` | `CceTransmission` → `CceEmsReport` → `CceEmsRecord` logical models |
| `input/fsh/codesystems.fsh` | `PqsE006DataObjects` (71 object codes), `PqsE003Alarms`, `CceEmdErrorCodes`, `CceLoggerErrorCodes` |
| `input/fsh/valuesets.fsh` | ValueSets backing the logical-model field bindings |
| `sushi-config.yaml` | SUSHI build config (`FSHOnly` — no full IG yet) |
| `input/maps/cce-interop-to-bundle.fml` | StructureMap: cce-interop EMS → FHIR Bundle |
| `transform/cce_to_fhir.py` | Executable reference transformer (lockstep with the FML) |
| `transform/run_phase2_poc.py` | PoC driver: generate → transform → validate |
| `decisions/` | Architecture decision records for the modeling choices |
| `examples/` | Generated `ems-transmission.json` + `ems-bundle.json` (gitignored — regenerate via the driver) |

## The transform (Option A)

Maps a cce-interop EMS transmission to a plain FHIR R4 **Bundle** of `Device` +
`Observation` resources:

- transmission `meta` → `Bundle` (`identifier`=transferId, `timestamp`=transferredAt)
- appliance / EMD / logger → `Device` hierarchy via `Device.parent`
- each numeric record object → `Observation` with `valueQuantity` + UCUM units and
  `effectiveInstant` (ABST normalized from ISO-basic to ISO-extended)
- `ALRM`/`EERR`/`LERR` → coded `Observation` (`valueCodeableConcept`); `MSW` → `valueBoolean`

```bash
pipenv sync --dev                          # includes fhir.resources
python fhir/transform/run_phase2_poc.py    # writes + validates examples/
python -m pytest tests/test_fhir_transform.py
```

`fhir.resources` is a FHIR-only dependency — not needed to run the simulator
itself, which is why it sits in `[dev-packages]` rather than `[packages]`. The
transform tests `importorskip` it, so they vanish silently when it is missing;
CI installs it so that coverage is always exercised.

### Authoritative validation with the HL7 FHIR Validator (Java)

The Python transformer output validates against **FHIR R4 proper (4.0.1)** using
HL7's own Java validator. Requires a JDK (17+) and `validator_cli.jar`:

```bash
cd fhir && npx fsh-sushi@latest . && cd ..      # CodeSystems for terminology checks
java -jar ~/fhir-validator/validator_cli.jar fhir/examples/ems-bundle-small.json \
     -ig fhir/fsh-generated/resources -version 4.0.1
# -> Success: 0 errors (warnings are best-practice only: no performer/narrative/display)
```

This is stricter than the pure-Python check and caught three real defects that
`fhir.resources` (R4B) missed, now fixed in `cce_to_fhir.py`:
`urn:uuid:` fullUrls must be real UUIDs (switched to resource-typed URLs);
RESTful fullUrls must end in `/{type}/{id}` matching the resource id;
`coding.display` must match the CodeSystem exactly (now omitted, the canonical
display lives in `PqsE006DataObjects`).

> **FML engine status.** The Java validator's `transform` mode *runs* a
> StructureMap, but the `.fml` does **not** yet execute cleanly: it has FML
> grammar issues and a source-shape gap (the FML reads the *grouped* logical-model
> paths, e.g. `report.appliance.AMFR`, while the cce-interop wire JSON is *flat*,
> `report.AMFR`). Making the FML engine-executable — and matching its output to the
> Python reference — remains open work. The Python transformer is the working
> executable reference today.

## Design notes

- **Cardinalities** follow the schema's `required` lists. `ABST` and `ADOP`/`EDOP`/etc.
  are typed as `instant`/`date` (the wire uses ISO-basic strings — normalized by the
  StructureMap).
- **Grouping**: the flat wire schema (e.g. `AMFR` at report root) is grouped here into
  `appliance` / `emd` / `logger` / `compressorUnit` / `location` BackboneElements for
  clarity. Flattening is a transform concern.
- **Corrected units** (vs. early draft): `HOLD` and `BEMD`/`BLOG` are in **days**,
  `SVA` in seconds, `CMPS` in rpm — per the authoritative Annex/schema definitions.
- **Alarms/errors**: `ALRM`/`EERR`/`LERR` modeled as `0..*` coded (wire format is a
  space-delimited string; absence = no alarm). How alarms are represented downstream
  is recorded in [`decisions/0001-alarm-modeling.md`](decisions/0001-alarm-modeling.md):
  every record keeps its coded `Observation` for lossless fidelity, and contiguous
  E003 alarm episodes are *additionally* derived into one `DetectedIssue` each. That
  derivation is an interoperability-layer concern — suppliers are not asked to emit it.

## Build

Requires Node. SUSHI is run via `npx` (no global install needed):

```bash
cd fhir
npx fsh-sushi@latest .
# -> fsh-generated/resources/*.json  (StructureDefinitions, CodeSystems, ValueSets)
```

`fsh-generated/` is build output and is gitignored.

## Roadmap

Implemented today: the logical models, the terminology, and the Option A transform
with its validation harness. Still open, roughly in order:

1. **Resolve the canonical namespace.** Everything is currently authored under a
   placeholder host; publishing requires an owner for the real namespace.
2. **Option B profiles + ConceptMaps to LOINC/UCUM**, packaged as a full
   Implementation Guide (HTML, narrative).
3. **Make the `.fml` engine-executable** and prove its output matches the Python
   reference transformer, under a Java-enabled CI job.
4. **Fold FHIR validation into the simulator ↔ validator conformance loop**, so a
   change to the delivery schema surfaces as a FHIR-side failure too.
