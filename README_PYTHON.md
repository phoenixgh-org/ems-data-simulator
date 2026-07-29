# Python Implementation

The reference Python implementation of the CCE thermal simulator. See [README.md](README.md) for architecture and physics documentation.

## Dependencies

Runtime: **Pydantic 2.x** (schema validation), plus `python-dateutil` and `pytz`. The simulation engine itself is pure Python standard library — only the schema layer (`ccesim/schemas.py`) needs Pydantic.

Development: pytest, `gibberish` (test fixtures), `fhir.resources` (the FHIR transform tests), numpy, pandas, matplotlib, locust (see `Pipfile`).

## Install

Requires Python 3.12. The distribution and the import package are both named
`ccesim`. It is not yet published to PyPI, so install from a clone.

To use the simulator as a library:

```bash
pip install -e .        # editable; drop -e for a normal install
```

To work on it, use pipenv — `Pipfile.lock` pins every dependency, and this is
what CI runs:

```bash
pipenv sync --dev       # installs the project editable, plus the dev stack
pipenv shell
```

Runtime dependencies are declared once, in `pyproject.toml`. `Pipfile` adds only
the development ones on top, so the two cannot drift.

Verify:

```bash
python3 -m pytest tests/ -q
```

## Quick start

### Low-level: SimulatedRecordSet

Generate records directly from the simulation engine:

```python
import datetime as dt
from ccesim.simulator import SimulatedRecordSet, default_config

config = default_config(power_type="mains", latitude=12.0)
start = dt.datetime(2024, 6, 15, 0, 0, 0)

rs = SimulatedRecordSet.generate(config, batch_size=96, start_time=start, interval=900)

# Raw dicts
for r in rs.records[:3]:
    print(r['ABST'], r['TVC'], r['TAMB'], r['CMPR'])

# Convert to Pydantic models
ems_records = rs.to_ems()       # List[EmsRecordMains]
rtmd_records = rs.to_rtmd()     # List[RtmdRecord]
```

### High-level: BaseRtmDevice

The device layer adds facility metadata, serial numbers, and schema-validated reports:

```python
from ccesim.device import MonitoringDeviceConfig, BaseRtmDevice

config = MonitoringDeviceConfig(
    type='ems',                # 'ems' or 'rtmd'
    upload_interval=3600,      # seconds between uploads
    sample_interval=900,       # seconds between samples
)
device = BaseRtmDevice(config)

# Generate sequential reports (state carries over between calls)
report = device.create_report(report_time=dt.datetime(2024, 6, 15, 12, 0))
print(type(report))  # EmsReport or RtmdReport
print(len(report.records))  # 3600/900 = 4
```

### Reported coordinates are deliberately jittered

Every report draws its `LAT`/`LNG` from `Facility.get_nudged_coordinates()`,
which adds a random offset of roughly 111 m (one sigma) to the facility's
coordinates. It is intentional — do not strip it as noise. It blurs the exact
point of a facility that may be a real one, and it means successive reports
from one device carry slightly different coordinates, as a real GPS fix would.

Two things follow. The offset is **not** anonymisation: 111 m is still inside
the compound, so treat it as courtesy, not as a privacy control. And it applies
to **your** facilities too — a list loaded through `Catalogs` or
`CCESIM_CATALOG_DIR` goes through the same path, so reported coordinates will
not match your registry exactly.

The jitter is report-only: `Facility.latitude` and `Facility.longitude` are
never mutated, only the emitted envelope moves. The JavaScript port applies the
same offset with the same parameters (see
[README_JAVASCRIPT.md](README_JAVASCRIPT.md)); the drawn values differ between
the two because the PRNGs differ, but the behaviour does not. Neither
implementation offers a switch to turn it off.

## Facility and equipment catalogs

Every device is drawn from three catalogs — a **facility**, an **appliance** and
a **logger** — held together by `ccesim.catalogs.Catalogs`. The packaged default
is a small illustrative sample (7 synthetic facilities from 27°N to 26°S, 6
appliances, 3 loggers), not a reference dataset. `Catalogs` lets you replace any
of the three with your own: a country's facility registry export, the equipment
actually deployed there, a manufacturer's own product line.

```python
from ccesim.catalogs import Catalogs

Catalogs()                                     # the packaged defaults
Catalogs(facilities=[...], appliances=[...])   # lists of dicts in hand
Catalogs.from_dir('./ke-catalog')              # facilities/appliances/loggers.{json,csv}
Catalogs.from_files(facilities='hfr_export.csv', appliances='fridges.json')
Catalogs.builtin('nigeria-sokoto')             # a named packaged catalog
```

**Anything not supplied falls back to the packaged default.** A country with
only its own facility list keeps the packaged WHO PQS equipment catalogs.
`from_files()` needs at least one of the three; the constructor takes lists of
dicts only, and refuses a path with a pointer to `from_files()`. Records are
normalized and validated on the way in, and the lists are copies — loading never
mutates the dicts you hand in, nor the packaged literals — so a `Catalogs`
object that exists is one every consumer can read without re-checking.

### Fields

A catalog is an array of records. Required fields are required per record;
everything else is optional, and unrecognized fields are kept verbatim.

| Catalog | Required | Optional (recognized) |
|---|---|---|
| `facilities` | `iso`, `latitude`, `longitude` | `OBJECTID`, `globalid`, `nhfr_uid`, `nhfr_facility_code`, `country`, `state`, `lga`, `lga_name_disagreement`, `ward`, `ward_name_disagreement`, `facility_name`, `facility_name_source`, `ownership`, `ownership_type`, `facility_level`, `facility_level_option`, `geocoordinates_source`, `last_updated` |
| `appliances` | `APQS`, `AMFR`, `AMOD`, `type` | `power_type` |
| `loggers` | `LPQS`, `LMFR`, `LMOD`, `type` | — |

Notes on individual fields:

- **`facility_name` is not required.** Only the three fields the simulator
  cannot do without are: `latitude` and `longitude` drive the ambient and solar
  models, and `iso` becomes the report's country id (`CID`). The recognized
  optional fields are
  exactly the ones `ccesim.facilities.Facility` reads; anything else you supply
  is preserved on the record but never read by the simulator.
- **`latitude` and `longitude` are coerced to `float`** and range-checked
  (±90 and ±180). A CSV cell that stays a string, or a registry export that
  dropped a decimal point (`1306.22`), is rejected here rather than reaching the
  ambient and solar models as nonsense.
- **`power_type` is `'solar'` or `'mains'`**, case- and whitespace-insensitive.
  Omit it and the power type is inferred from the free-text `type` string. State
  anything else — `diesel` — and the load fails naming the file, the row and the
  appliance, because the power type selects the entire physical model.

### Both key spellings are accepted

An unmodified WHO PQS export uses `APQS`/`AMFR`/`AMOD` for appliances and
`LPQS`/`LMFR`/`LMOD` for loggers. A country's own list is far more likely to say
`pqs_code`/`manufacturer`/`model`. Both load, and both produce the same record —
the PQS-style form the rest of the package reads.

| Stored as | Also accepted as |
|---|---|
| `APQS` | `pqs_code`, `pqs` |
| `AMFR` | `manufacturer` |
| `AMOD` | `model` |
| `LPQS` | `pqs_code`, `pqs` |
| `LMFR` | `manufacturer` |
| `LMOD` | `model` |
| `type` | `appliance_type` (appliances); `logger_type`, `device_type` (loggers) |
| `power_type` | `powertype`, `power_source` |
| `latitude` | `lat` |
| `longitude` | `lon`, `lng`, `long` |
| `facility_name` | `name`, `facility` |
| `iso` | `iso3`, `iso_code`, `country_code` |
| `nhfr_facility_code` | `facility_code` |

**Case, spaces and hyphens are folded** before the table is consulted, so a
spreadsheet header row of `Facility Name,ISO,Lat,Long` loads exactly like
`facility_name,iso,latitude,longitude`, and `Power-Type` works too.

**Unrecognized keys ride along untouched.** A column named `openlmis_id` or
`Our Ref` is stored under that exact name, so your own join keys survive the
round trip.

**Two columns meaning the same field is an error**, not a resolution by luck: a
file with both `APQS` and `pqs_code`, or with `latitude` twice, or with
`latitude` and `Latitude`, is rejected naming both columns. `csv.DictReader`
would otherwise silently keep the last value — a plausible wrong latitude
reaching the thermal model. The check runs on the header row alone, so a file
with no data rows still fails on the duplicate rather than merely reporting an
empty catalog. Genuinely distinct columns that merely look alike (`lga` and
`lga_name_disagreement`) are unaffected.

### File formats

**JSON is an array of objects**, matching the shape of the packaged literals:

```json
[
  {"facility_name": "Kericho County Referral Hospital", "iso": "KEN",
   "latitude": -0.3689, "longitude": 35.2861}
]
```

A JSON payload that is not an array is an error naming the file; an element that
is not an object is an error naming the file and the record number; an empty
array is an error too — a catalog file that supplies nothing is a mistake, not a
fall back.

**CSV is a header row plus one row per record** — what a country program
actually has, because the facility list comes out of an HFR or OpenLMIS as a
spreadsheet:

```csv
facility_name,iso,latitude,longitude
Kericho County Referral Hospital,KEN,-0.3689,35.2861
```

CSV quirks the loader handles deliberately:

- **A UTF-8 byte order mark** from Excel does not become part of the first
  column name.
- **Blank cells mean "not stated", not the empty string**, and are dropped. That
  is what lets a `power_type` column filled in for only some appliances load at
  all — the blank rows fall back to the type sniff. A blank cell in a *required*
  column still fails the missing-field check. (JSON has a real `null` for this;
  an explicitly empty string in JSON is still an error.)
- **Trailing empty columns** — the classic Excel "Save as CSV" artefact where
  every line ends in extra commas — load and are dropped, rather than reading as
  an unnamed column duplicated.
- **A row with more values than the header has columns** is an error.
- **An empty file** is an error: a header row is expected.

In a directory, extensions are matched case-insensitively (`facilities.CSV` from
Excel and several GIS exporters is found), as are file names (`Facilities.csv`).
Two files claiming the same catalog — `facilities.csv` beside `facilities.JSON`,
or beside `Facilities.csv` — is an error rather than a resolution by luck. Files
with any other extension are ignored by `from_dir()`, so a `README` or a
leftover `.xlsx` in the directory is harmless; naming one explicitly to
`from_files()` is an error instead. A directory with no catalog file at all is
an error, listing the names it looked for.

### Where the catalogs come from

`MonitoringDeviceConfig` resolves its catalogs in this order:

1. **An explicit `catalogs=` argument** — highest precedence.
2. **`CCESIM_CATALOG_DIR`**, naming a catalog directory. This is what makes the
   feature zero-code: it works for `locustfile.py`, the notebook and any
   downstream script unchanged.
3. **The packaged defaults.**

```python
from ccesim.catalogs import Catalogs
from ccesim.device import MonitoringDeviceConfig

# 1. Explicit — wins over everything
config = MonitoringDeviceConfig(type='ems', catalogs=Catalogs.from_dir('./ke-catalog'))

# 2. Environment — no code change at all
#    $ CCESIM_CATALOG_DIR=./ke-catalog python3 -m locust -f locustfile.py
config = MonitoringDeviceConfig(type='ems')
```

An **unusable `CCESIM_CATALOG_DIR` is an error**, never a quiet fall back to the
packaged catalogs: a user who set it meant it, and silently simulating the
packaged example facilities instead of their own country is the failure the
module exists to prevent. An unset or empty value means "not asked for", which
is what an exported-but-blank variable in a shell profile means in practice.

The resolved catalogs are **cached** — a load test building thousands of devices
reads the files once, and every device shares one `Catalogs` object. Call
`ccesim.catalogs.reset_default_catalogs()` to make the next resolution re-read
the environment.

### Named packaged catalogs

`Catalogs.builtin(name)` loads a catalog shipped with the simulator:

| Name | Carries |
|---|---|
| `'default'` | The illustrative sample: 7 facilities, 6 appliances, 3 loggers |
| `'nigeria-sokoto'` | The 46 real Sokoto State (Nigeria) facilities |
| `'pqs-e003-full'` | The whole prequalified equipment catalogue: 96 appliances, 13 loggers |

**A builtin only replaces the catalogs it names**; the rest stay the packaged
default. So `Catalogs.builtin('nigeria-sokoto')` is the real Sokoto facility
list against the *sample* equipment, and `Catalogs.builtin('pqs-e003-full')` is
the full equipment lists against the *sample* facilities. This is deliberate —
it follows the same "anything not supplied falls back" rule as `from_dir()`.

To reconstruct the full set the simulator used to ship as its default — 46
Sokoto facilities, 96 appliances and 13 loggers together — compose the module
literals directly:

```python
from ccesim.catalogs import Catalogs
from ccesim.facilities import nigeria_sokoto_facilities
from ccesim.devicegroups import pqs_e003_fridges, pqs_e006_rtmds

Catalogs(facilities=nigeria_sokoto_facilities,
         appliances=pqs_e003_fridges, loggers=pqs_e006_rtmds)
```

Records passed in hand carry no provenance, so that object's `.manifest` is
empty. The Sokoto facilities are CC BY 4.0 and their licence makes citing the
source a condition of use, so if you redistribute anything derived from this
composition, carry the provenance across too:

```python
sokoto = Catalogs.builtin('nigeria-sokoto').manifest
equipment = Catalogs.builtin('pqs-e003-full').manifest

catalogs = Catalogs(
    facilities=nigeria_sokoto_facilities,
    appliances=pqs_e003_fridges,
    loggers=pqs_e006_rtmds,
    manifest={
        'facilities': sokoto['facilities'],
        'appliances': equipment['appliances'],
        'loggers': equipment['loggers'],
    },
)
print(catalogs.manifest['facilities']['citation'])
```

### Provenance: `manifest.json`

A catalog may say where it came from. `from_dir()` reads an optional
`manifest.json` from beside the catalog files and exposes it as
`Catalogs.manifest`:

```json
{
  "facilities": {
    "source": "Kenya Master Health Facility List",
    "vintage": "2025 Q1",
    "licence": "Open Government Licence",
    "url": "https://example.gov.ke/mfl",
    "retrieved": "2025-03-14"
  }
}
```

- **It is keyed by catalog kind** — `facilities`, `appliances`, `loggers` —
  because provenance genuinely differs between them: a country brings its own
  facility list but keeps the packaged WHO PQS equipment catalogs. A top-level
  key that is not one of the three is an error.
- **The fields are a convention, not a schema.** `source`, `vintage`, `licence`,
  `url`, `retrieved` and `citation` are what this project uses; the loader
  neither requires them nor rejects others, and never interprets a value. A
  licence here is a string a human reads, not a controlled term. Add your own
  fields — a `contact`, your own terms — and they survive.
- **It is entirely optional**, and its absence is silent: no warning, no log
  line. Most third-party catalogs will not have one.
- **It describes only the catalogs you actually supplied.** A manifest entry for
  a catalog with no file in the directory is an error — otherwise the packaged
  default appliances would be labelled with someone else's provenance. Kinds
  that fell back report the *packaged* provenance instead, so `from_dir()` on a
  directory holding only facilities still reports the WHO PQS origin of the
  appliances it did not replace.
- The name is matched case-insensitively (`Manifest.json` is found), and two
  manifests in one directory is an error.
- **The packaged catalogs carry theirs in code**, since they are literals rather
  than files: `Catalogs().manifest['facilities']['source']` says the sample
  facilities are synthetic, and `Catalogs.builtin('nigeria-sokoto')` carries the
  GRID3 v2.0 citation its CC BY 4.0 licence requires.

A manifest can also be passed straight to the constructor alongside records in
hand:

```python
Catalogs(facilities=rows, manifest={'facilities': {'source': 'Our own export'}})
```

### Worked example: a small custom catalog

A three-facility Kenyan catalog, with its own equipment list and its own join
keys, falling back to the packaged loggers.

`ke-catalog/facilities.csv` — spreadsheet headers, straight out of a registry
export, plus an OpenLMIS id the loader does not recognize and keeps anyway:

```csv
Facility Name,ISO,state,Lat,Long,openlmis_id
Kericho County Referral Hospital,KEN,Kericho,-0.3689,35.2861,OLMIS-1041
Londiani Sub-County Hospital,KEN,Kericho,-0.1656,35.5906,OLMIS-1042
Kisumu East DVS,KEN,Kisumu,-0.0917,34.7680,OLMIS-2213
```

`ke-catalog/appliances.json` — plain key spelling, plus an asset tag:

```json
[
  {
    "pqs_code": "E003/007",
    "manufacturer": "Vestfrost Solutions",
    "model": "MK 304",
    "type": "Icelined refrigerator",
    "power_type": "mains",
    "asset_tag": "KE-CCE-0001"
  },
  {
    "pqs_code": "E003/030",
    "manufacturer": "B Medical Systems Sarl",
    "model": "TCW 3000 SDD",
    "type": "Solar direct drive refrigerator",
    "power_type": "solar",
    "asset_tag": "KE-CCE-0002"
  }
]
```

`ke-catalog/manifest.json` — describing only the two catalogs the directory
actually supplies:

```json
{
  "facilities": {
    "source": "Kenya Master Health Facility List",
    "vintage": "2025 Q1",
    "licence": "Open Government Licence",
    "url": "https://example.gov.ke/mfl",
    "retrieved": "2025-03-14"
  },
  "appliances": {
    "source": "National cold chain inventory export",
    "retrieved": "2025-03-14"
  }
}
```

There is no `loggers` file, so the packaged loggers stay — and report their own
provenance.

```python
import datetime as dt
from ccesim.catalogs import Catalogs
from ccesim.device import MonitoringDeviceConfig, BaseRtmDevice

catalogs = Catalogs.from_dir('./ke-catalog')
print(catalogs)
# Catalogs(facilities=3, appliances=2, loggers=3)

# Spreadsheet headers folded; coordinates are floats; join keys kept.
print(catalogs.facilities[0]['facility_name'], catalogs.facilities[0]['latitude'])
# Kericho County Referral Hospital -0.3689
print(catalogs.facilities[0]['openlmis_id'])
# OLMIS-1041

# Plain keys stored in the PQS-style form; asset_tag rides along.
print(catalogs.appliances[0]['APQS'], catalogs.appliances[0]['AMOD'])
# E003/007 MK 304
print(catalogs.appliances[0]['asset_tag'])
# KE-CCE-0001

# The loggers fell back, so they report the packaged provenance.
print(catalogs.manifest['loggers']['source'])
# Three remote temperature monitoring devices sampled from the WHO PQS ...

config = MonitoringDeviceConfig(
    type='ems', upload_interval=3600, sample_interval=900, catalogs=catalogs,
)
report = BaseRtmDevice(config).create_report(report_time=dt.datetime(2024, 6, 15, 12, 0))
print(len(report.records))
# 4
```

Or with no code change at all:

```bash
CCESIM_CATALOG_DIR=./ke-catalog python3 your_script.py
```

## Injecting anomalies

```python
from ccesim.simulator.config import FaultType, default_config

config = default_config("mains", latitude=12.0)

# Compressor failure
config.fault.fault_type = FaultType.COMPRESSOR_FAILURE
config.fault.fault_start_offset_s = 8 * 3600    # fail at hour 8
config.fault.fault_duration_s = 6 * 3600         # lasts 6 hours (0 = permanent)

# Refrigerant leak
config.fault.fault_type = FaultType.REFRIGERANT_LEAK
config.fault.fault_start_offset_s = 0
config.fault.fault_duration_s = 0                # permanent
config.fault.refrigerant_leak_rate = 0.02        # 2% capacity loss per hour

# Combining door presets with faults
from ccesim.simulator.config import EventConfig, FaultConfig

config.events = EventConfig.few_but_long()
config.fault = FaultConfig(
    fault_type=FaultType.POWER_OUTAGE,
    fault_start_offset_s=3 * 86400,   # power fails on day 3
    fault_duration_s=24 * 3600,
)
```

## Generating multi-day datasets

```python
config = MonitoringDeviceConfig(type='ems', upload_interval=3600, sample_interval=900)
device = BaseRtmDevice(config)

t = dt.datetime(2024, 1, 1, 0, 0, 0)
all_reports = []
for _ in range(24 * 30):  # 30 days of hourly reports
    report = device.create_report(report_time=t)
    all_reports.append(report)
    t += dt.timedelta(hours=1)
```

State (TVC, compressor status, logger battery SOC, RNG) carries over between calls automatically via `SimulatorState`.

## Example configurations

### Small mains-powered chest fridge

```python
from ccesim.simulator.config import SimulationConfig, ThermalConfig, AmbientConfig, PowerConfig, EventConfig

config = SimulationConfig(
    thermal=ThermalConfig(
        R=0.08,              # Poor insulation
        C=10000.0,           # Small thermal mass
        Q_compressor=200.0,
        R_door=0.12,         # Large door = lower resistance
        T_setpoint_low=2.0,
        T_setpoint_high=8.0,
    ),
    ambient=AmbientConfig(T_mean=32.0, T_amplitude=4.0),
    power=PowerConfig(power_type="mains"),
    events=EventConfig(
        door_rate_per_hour=5.0,
        door_mean_duration_s=45.0,
    ),
)
```

### Well-insulated walk-in cold room

```python
config = SimulationConfig(
    thermal=ThermalConfig(
        R=0.20,
        C=500000.0,
        Q_compressor=500.0,
        R_door=0.10,
        T_setpoint_low=2.0,
        T_setpoint_high=6.0,
    ),
    ambient=AmbientConfig(T_mean=25.0, T_amplitude=3.0),
    power=PowerConfig(power_type="mains"),
    events=EventConfig(
        door_rate_per_hour=8.0,
        door_mean_duration_s=60.0,
        working_hours=(6, 22),
    ),
)
```

## Locust load testing

The `locustfile.py` integrates the simulator with [Locust](https://locust.io/) for load testing a CCE data ingestion endpoint. Each Locust user represents a single CCE device sending a pre-generated series of CCE Data Delivery reports.

During startup, each virtual user creates a `BaseRtmDevice`, pre-generates a queue of sequential reports, then POSTs them one at a time. State carries over between reports for physical continuity. Load volume comes from spawning many users (each a distinct device), not from time compression.

### Configuration

| Environment variable | Default | Description |
|---|---|---|
| `TARGET_HOST` | `http://localhost:8001` | Base URL of the ingestion endpoint |
| `INGEST_PATH` | `/` | Path on `TARGET_HOST` that reports are POSTed to |
| `NUM_REPORTS` | `168` | Reports per device (168 = one week at 1h intervals) |
| `SIM_START` | `2024-06-15T00:00:00` | Simulated start date (ISO 8601) |
| `START_JITTER_S` | `3600` | Max random offset per user's start time |

### Delivery transport (CCE data delivery spec compliance)

The POST is configurable to comply with the [CCE data delivery requirements](../WHO_PQS_E006_EMS_specifications/data_delivery/). All settings below default to spec-compliant, backward-compatible behavior — with none set, reports are sent as plain UTF-8 JSON with no authentication.

| Environment variable | Default | Description |
|---|---|---|
| `CHARSET` | `utf-8` | Charset declared in the `Content-Type` header (§1.1/§1.2). Sent as `application/json; charset=<CHARSET>` |
| `AUTH_HEADER` | `x-api-key` | Name of the header carrying the auth token (§1.3); configurable per employer |
| `AUTH_SCHEME` | _(empty)_ | Optional scheme prefix for the token value (e.g. `Bearer`, `Basic`). Empty = bare token |
| `AUTH_TOKEN` | _(unset)_ | The opaque auth token. **When unset, no auth header is sent** (auth disabled) |
| `GZIP` | _(off)_ | When truthy (`1`/`true`/`yes`/`on`), gzip-compress the request body as raw binary and set `Content-Encoding: gzip` (§1.6). Body size is checked against the 1 MB post-compression cap (§1.4) |

Authentication covers all three shapes the spec allows (plus standard Bearer) from one mechanism:

```bash
# API-key in a named header (spec §1.3 default)
AUTH_HEADER=x-api-key AUTH_TOKEN=<key>            # -> x-api-key: <key>

# Bearer token (e.g. OAuth-protected employer endpoint)
AUTH_HEADER=Authorization AUTH_SCHEME=Bearer AUTH_TOKEN=<token>
                                                 # -> Authorization: Bearer <token>

# HTTP Basic auth (spec §1.3)
AUTH_HEADER=Authorization AUTH_SCHEME=Basic AUTH_TOKEN=<base64(user:pass)>
                                                 # -> Authorization: Basic <b64>
```

> **Note:** gzip bodies are sent as raw binary and are never additionally Base64-encoded, per §1.6.

### Examples

```bash
# 100 virtual devices, ramping 5 users/second
export INGEST_PATH="/your/ingest/path"
locust -f locustfile.py --headless -u 100 -r 5

# 30 days of data per device
NUM_REPORTS=720 locust -f locustfile.py --headless -u 50 -r 10

# Remote endpoint with custom start date
TARGET_HOST=https://ingest.example.org SIM_START=2025-01-01T00:00:00 \
  locust -f locustfile.py --headless -u 500 -r 20

# Spec-compliant delivery: Bearer auth + gzip-compressed bodies
TARGET_HOST=https://ingest.example.org INGEST_PATH=/v1/cce \
  AUTH_HEADER=Authorization AUTH_SCHEME=Bearer AUTH_TOKEN=$MY_TOKEN GZIP=true \
  locust -f locustfile.py --headless -u 100 -r 5
```

## Adding a new power type

To support a new power source (e.g., generator-backed, hybrid solar-mains):

1. Create a new model class in `ccesim/simulator/power.py` implementing `simulate_interval()` and `is_power_available()`
2. Add a branch in `SimulatedRecordSet.generate()` to instantiate it
3. Add any new output fields to the `to_ems()` / `to_rtmd()` conversion methods

## Project structure

```
ccesim/
├── __init__.py              Package marker
├── simulator/
│   ├── __init__.py          Public API exports
│   ├── config.py            All configuration dataclasses
│   ├── thermal.py           RC thermal model, ambient model, door events
│   ├── power.py             Mains and solar power models
│   ├── events.py            Door generation, fault injection, alarms
│   └── recordset.py         Orchestration and schema conversion
├── catalogs.py              Pluggable facility and equipment catalog loader
├── device.py                High-level device + report generation
├── devicegroups.py          Sample PQS equipment catalog (+ the full E003/E006 lists)
├── facilities.py            Sample facility catalog (synthetic, 27°N–26°S)
├── generator.py             Serial numbers, transfer metadata
└── schemas.py               Pydantic models (cce-interop 0.8.1 schema)

tests/
├── __init__.py              Package marker
├── conftest.py              Shared fixtures (serials, timestamps, sample reports)
├── test_thermal.py          Thermal model unit tests
├── test_power.py            Power model unit tests
├── test_events.py           Events, faults, alarms unit tests
├── test_recordset.py        Integration tests
├── test_generation.py       Device + report end-to-end tests
├── test_facilities.py       Facility data tests
├── test_catalogs.py         Pluggable catalog loader tests
├── test_power_type.py       Appliance power-type resolution tests
├── test_alarm_episodes.py   Alarm episode derivation tests (FHIR DetectedIssue)
├── test_fhir_transform.py   cce-interop to FHIR R4 Bundle transform tests
└── test_rtmd.py             Schema validation tests

fhir/                        FHIR IG and reference transform (see fhir/README.md)
locustfile.py                Locust load test configuration
simulator_examples.ipynb     Interactive examples with plots
```

## Running tests

```bash
python3 -m pytest tests/ -v
```
