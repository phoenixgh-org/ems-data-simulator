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
├── test_thermal.py          Thermal model unit tests
├── test_power.py            Power model unit tests
├── test_events.py           Events, faults, alarms unit tests
├── test_recordset.py        Integration tests
├── test_generation.py       Device + report end-to-end tests
├── test_facilities.py       Facility data tests
├── test_catalogs.py         Pluggable catalog loader tests
├── test_power_type.py       Appliance power-type resolution tests
└── test_rtmd.py             Schema validation tests

locustfile.py                Locust load test configuration
simulator_examples.ipynb     Interactive examples with plots
```

## Running tests

```bash
python3 -m pytest tests/ -v
```
