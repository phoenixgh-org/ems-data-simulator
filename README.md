# CCE Thermal Simulator

[![CI](https://github.com/phoenixgh-org/ems-data-simulator/actions/workflows/ci.yml/badge.svg)](https://github.com/phoenixgh-org/ems-data-simulator/actions/workflows/ci.yml)

A physics-based synthetic data generator for cold chain equipment (CCE) monitoring systems. Produces realistic time-series data conforming to the **CCE Data Delivery** specification — the draft standard for delivering vaccine refrigerator monitoring data from equipment suppliers to national systems — for both EMS (Equipment Monitoring System) and RTMD (Remote Temperature Monitoring Device) transfer types.

- Specification and schema drafts: <https://docs.2to8.cc/cce-data-interop/overview/>
- Schema version emitted: **`cce-interop` 0.8.1**

### Who this is for

Anyone who needs realistic CCE monitoring data but does not have access to a real fleet:

- **Country / employer system implementers** building the ingestion side of the CCE Data Delivery spec, who need conformant payloads to test against before any supplier is connected.
- **Equipment suppliers and integrators** validating their own delivery implementation.
- **Researchers and tool builders** who need temperature time series with known, labelled fault conditions — the ground truth that real fleet data never comes with.

The simulator generates data entirely from first principles. It needs no database, no network, and no external data source: the temperature series is produced by integrating a thermal model of the refrigerator, not by replaying recorded data.

Available in two implementations:

- **[Python](README_PYTHON.md)** — the reference implementation, with Pydantic schemas, Locust load testing, and Jupyter notebook examples
- **[JavaScript](README_JAVASCRIPT.md)** — a port for use in JS applications, with a seedable PRNG and no external dependencies beyond that

## Install and quick start

### Python

Not yet on PyPI; install from source. The package is named `ccesim`.

```bash
git clone https://github.com/phoenixgh-org/ems-data-simulator.git
cd ems-data-simulator
pip install -e .          # or: pipenv sync --dev, for the full dev environment
```

Generate one day of 15-minute records from a mains-powered fridge in a tropical climate:

```python
import datetime as dt
from ccesim.simulator import SimulatedRecordSet, default_config

config = default_config(power_type="mains", latitude=12.0)
rs = SimulatedRecordSet.generate(
    config, batch_size=96, start_time=dt.datetime(2024, 6, 15), interval=900,
)

for r in rs.records[:3]:
    print(r["ABST"], r["TVC"], r["TAMB"], r["CMPR"])
```

To emit a complete, schema-conformant transmission instead of raw records, use the device layer:

```python
from ccesim.device import MonitoringDeviceConfig, BaseRtmDevice

device = BaseRtmDevice(MonitoringDeviceConfig(type="ems", upload_interval=3600, sample_interval=900))
report = device.create_report(report_time=dt.datetime(2024, 6, 15, 12, 0))
```

Verify the install:

```bash
python3 -m pytest tests/ -q
```

See **[README_PYTHON.md](README_PYTHON.md)** for fault injection, multi-day datasets, and Locust load testing.

### JavaScript

```bash
cd js && npm install
```

```javascript
import { SimulatedRecordSet, defaultConfig } from './src/index.js';

const config = defaultConfig('mains', 12.0);
config.random_seed = 42;                     // reproducible output
const rs = SimulatedRecordSet.generate(config, 96, new Date(Date.UTC(2024, 5, 15)), 900);

console.log(rs.records.slice(0, 3));
```

Verify the install:

```bash
cd js && npm test
```

See **[README_JAVASCRIPT.md](README_JAVASCRIPT.md)** for the full API reference.

## Facility and equipment catalogs

Every simulated device is drawn from three catalogs: a **facility** (its
coordinates drive the ambient and solar models), an **appliance** (the fridge or
freezer), and a **logger**. The packaged default is a small illustrative sample
— seven synthetic facilities spanning 27°N to 26°S, six appliances, three
loggers — sized to demonstrate the simulator, **not** to describe any country's
real estate. Bring your own by pointing the simulator at a catalog directory:

```
ke-catalog/
├── facilities.csv     # or facilities.json
├── appliances.json    # or appliances.csv
├── loggers.json       # or loggers.csv
└── manifest.json      # optional: where each catalog came from
```

Each catalog is an array of records — a JSON array of objects, or a CSV with a
header row. A catalog with no file falls back to the packaged default, so a
country that has only its own facility list keeps the packaged WHO PQS
equipment catalogs.

| Catalog | Required fields | Common optional fields |
|---|---|---|
| `facilities` | `iso`, `latitude`, `longitude` | `facility_name`, `country`, `state`, `lga`, `ward`, `ownership`, `facility_level`, `nhfr_uid`, … |
| `appliances` | `APQS`, `AMFR`, `AMOD`, `type` | `power_type` (`solar` or `mains`) |
| `loggers` | `LPQS`, `LMFR`, `LMOD`, `type` | — |

Field names are normalized on load, so an unmodified WHO PQS export and a
country's own spreadsheet both drop straight in: `pqs_code`/`manufacturer`/
`model` are accepted for the `APQS`/`AMFR`/`AMOD` (and `LPQS`/`LMFR`/`LMOD`)
forms, `Facility Name`, `Lat` and `Long` are accepted for `facility_name`,
`latitude` and `longitude`, and case, spaces and hyphens are folded. Columns the
loader does not recognize ride along untouched, so your own join keys survive.

Validation happens at load and is loud: a facility with no latitude fails
naming the file and the row, rather than reaching the thermal model as a `None`.

**Reported coordinates are deliberately jittered.** Both implementations add a
fresh random offset of roughly 111 m (one sigma) to `LAT`/`LNG` on every
report — it blurs the exact point of a facility that may be a real one, and
makes successive reports vary as a real GPS fix would. It is not anonymisation,
it never mutates the stored facility coordinates, and it applies to catalogs you
supply, so reported coordinates will not match your registry exactly. See
[README_PYTHON.md](README_PYTHON.md) and
[README_JAVASCRIPT.md](README_JAVASCRIPT.md).

Catalog field names are **snake_case in both implementations**. A catalog file
is configuration, not API surface: the Python API is snake_case and the
JavaScript API is camelCase, but the field names inside a catalog file are not
camelCased on the JS side, so one file can be read by both ports without a
translation layer.

See **[README_PYTHON.md](README_PYTHON.md#facility-and-equipment-catalogs)** for
the full field reference, the `CCESIM_CATALOG_DIR` environment variable, the
provenance manifest, and a complete worked example.

## Architecture

```
SimulationConfig
    ├── ThermalConfig      R, C, Q_compressor, setpoints
    ├── AmbientConfig      T_mean, T_amplitude, daily cycle
    ├── PowerConfig        mains outages / solar bell curve
    ├── EventConfig        door opening rates
    └── FaultConfig        fault injection parameters

SimulatedRecordSet.generate(config, batch_size, start_time)
    ├── AmbientModel       → TAMB (sinusoidal + noise)
    ├── ThermalModel       → TVC, CMPR, DORV, HOLD (RC circuit + thermostat + icebank reserve)
    ├── PowerModel         → SVA/ACCD/ACSV or DCSV/DCCD/BLOG
    ├── DoorEventGenerator → door openings (Poisson process)
    ├── FaultInjector      → fault effects on thermal/power
    └── AlarmGenerator     → ALRM, EERR, LERR
```

## Thermal model

The vaccine chamber temperature (TVC) is governed by an RC-circuit ODE:

```
dTVC/dt = (TAMB - TVC) / (R * C)
        - (Q_compressor * compressor_on) / C
        + (TAMB - TVC) / (R_door * C) * door_open
```

The thermostat uses hysteresis control: the compressor turns ON when TVC reaches `T_setpoint_high` and turns OFF when TVC drops to `T_setpoint_low`. This produces the characteristic sawtooth pattern seen in real fridge data.

Integration uses the Euler method with configurable sub-steps (default 10s) within each sample interval (typically 600s or 900s).

### Two-node model

When `C_air > 0`, the model splits the chamber into a fast "air" node (what the TVC probe reads) and a slow "contents" node (bulk thermal mass). Heat flows between the two via `R_air_contents`. This captures the real-world behavior where air temperature spikes during door openings but contents remain stable.

### Icebank

Solar direct drive fridges store energy as ice rather than in batteries. When `icebank_capacity_j > 0`, the model includes a phase-change thermal reservoir at 0 C. While charged, it absorbs heat and holds TVC near freezing. When depleted, TVC rises toward ambient.

## Power models

**Mains-powered** fridges have continuous power with stochastic outages modeled as a Poisson process. During an outage, the compressor cannot run and TVC drifts toward ambient.

**Solar direct drive (SDD)** fridges run the compressor directly from solar panels — there is no electrical battery for the compressor. Solar voltage follows a bell curve from sunrise to sunset. Energy is stored thermally in ice lining, not electrically. The BLOG field reflects a small backup battery that keeps the data *logger* running overnight; it cannot power the compressor.

## Fault injection

Four fault types produce the kinds of anomalies seen in real CCE deployments:

| Fault | Effect | Typical signature |
|-------|--------|-------------------|
| **Compressor failure** | Compressor stops | TVC drifts to ambient |
| **Power outage** | Power forced off | CMPR=0, TVC rises |
| **Stuck door** | Door forced open | High DORV, TVC rises even with compressor |
| **Refrigerant leak** | Cooling capacity decays exponentially | Gradual TVC rise over days/weeks |

Faults compose with stochastic elements (door openings, ambient noise, mains outages) to produce realistic compound events.

## Door behavior presets

`EventConfig` provides five named presets calibrated from fleet-wide analysis of 1,225 fridges (Jan 2021 - Dec 2022):

| Preset | opens/day | secs/day | TVC max | HEAT alarms | Pattern |
|---|---|---|---|---|---|
| `bestpractice()` | ~2 | ~60 | 7.1 C | 0 | Fleet median — trained staff |
| `normal()` | ~6 | ~160 | 7.3 C | 0 | Typical facility, adequate practices |
| `frequent_short()` | ~10 | ~290 | 7.3 C | 0 | Many brief opens, marginal |
| `busy_facility()` | ~16 | ~440 | 8.0 C | 0 | High-traffic / campaign days |
| `few_but_long()` | ~3 | ~530 | 13.1 C | 12 | Extended opens, causes excursions |

Preset names are shown in their Python spelling. The JavaScript port follows JS
convention and names them `bestpractice()`, `normal()`, `frequentShort()`,
`busyFacility()`, and `fewButLong()`.

## WHO alarm codes

The alarm generator derives WHO PQS E003 alarm codes from simulation state:

| Code | Condition | Threshold |
|------|-----------|-----------|
| HEAT | TVC > 8 C continuously | 10 hours |
| FRZE | TVC <= -0.5 C continuously | 60 minutes |
| DOOR | Door open continuously | 5 minutes |
| POWR | No power continuously | 24 hours |

Alarm excursion timers persist across sample intervals, so a HEAT alarm can accumulate over multiple 15-minute records.

## Calibration

The defaults are not invented. They are fitted to real-world performance data from over 1,000 Aucma MetaFridge CFD-50 devices deployed in Nigeria and Kenya. That underlying dataset is operational fleet data held by Phoenix Global Health and is **not public**, so it is not distributed with this repository — but the behaviour it produced is captured in the defaults, and the resulting output characteristics are described below so they can be checked against your own fleet.

Solar direct drive defaults reproduce these observed characteristics:

- TVC remarkably stable at 3.6-4.2 C (ice-lined thermal mass)
- Compressor runs only during solar hours (~22% of intervals)
- DCSV follows a clean bell curve peaking at ~20V
- BLOG (logger battery) charges during the day, drains slowly overnight

The refrigerant leak decay rate (default 0.002/hour) is fitted to a 62-day degradation timeline observed on a single reference unit in that fleet.

The door behaviour presets below are calibrated separately, from a fleet-wide analysis of 1,225 fridges over Jan 2021 - Dec 2022.

## Extending for different refrigerator types

The simulator is parameterized to support a range of thermal characteristics.

### Parameter guide

| Parameter | Effect | Typical range |
|-----------|--------|---------------|
| `R` | Thermal resistance (insulation quality) | 0.08 (poor) - 0.35 (ice-lined) |
| `C` | Thermal capacitance (thermal mass) | 10,000 (small chest) - 2,000,000 (ice-lined SDD) |
| `Q_compressor` | Cooling power | 150 - 400 W |
| `R_door` | Thermal resistance of open doorway | 0.10 (large door) - 0.30 (chest lid) K/W |
| `T_setpoint_low` | Compressor OFF threshold | 2 - 4 C |
| `T_setpoint_high` | Compressor ON threshold | 5 - 8 C |

The **equilibrium temperature** when the compressor is running continuously is:

```
TVC_eq = TAMB - Q_compressor * R
```

This must be well below `T_setpoint_low` for the thermostat cycle to work. For example, with `TAMB=28`, `Q=300`, `R=0.12`: `TVC_eq = 28 - 36 = -8 C`.

The **time constant** `tau = R * C` controls how quickly TVC responds to changes. Larger tau means slower, more stable temperature swings.

## License

See [LICENSE](LICENSE).
