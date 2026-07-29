# JavaScript Implementation

A JavaScript port of the CCE thermal simulator for use in JS applications. See [README.md](README.md) for architecture and physics documentation.

## Dependencies

**Production:** [`seedrandom`](https://www.npmjs.com/package/seedrandom) for deterministic PRNG. No other runtime dependencies.

**Development:** [vitest](https://vitest.dev/) for testing.

## Install

```bash
cd js
npm install
```

## Quick start

### Low-level: SimulatedRecordSet

```javascript
import { SimulatedRecordSet, defaultConfig } from './src/index.js';

const config = defaultConfig('mains', 12.0);
config.random_seed = 42;
const start = new Date(Date.UTC(2024, 5, 15, 0, 0, 0));

const rs = SimulatedRecordSet.generate(config, 96, start, 900);

// Raw records
for (const r of rs.records.slice(0, 3)) {
  console.log(r.ABST, r.TVC, r.TAMB, r.CMPR);
}

// Convert to schema objects
const emsRecords = rs.toEms();    // EmsRecordMains[]
const rtmdRecords = rs.toRtmd();  // RtmdRecord[]

// Serialize to JSON
const json = JSON.stringify(rtmdRecords.map(r => r.toJSON()));
```

### High-level: BaseRtmDevice

The device layer adds metadata and sequential report generation:

```javascript
import { MonitoringDeviceConfig, BaseRtmDevice } from './src/index.js';

const config = new MonitoringDeviceConfig({
  type: 'rtmd',
  uploadInterval: 3600,
  sampleInterval: 900,
  powerType: 'mains',
  // Appliance identity
  amfr: 'Aucma',
  amod: 'CFD-50',
  apqs: 'E003/040',
  // Facility
  cid: 'facility-001',
  lat: 12.0,
  lng: 8.5,
});

const device = new BaseRtmDevice(config);

// Generate sequential reports (state carries over)
const report = device.createReport(new Date(Date.UTC(2024, 5, 15, 12, 0, 0)));
console.log(report.toJSON());
```

### Reported coordinates are deliberately jittered

Every report adds a random offset of roughly 111 m (one sigma) to the `lat`/
`lng` you configured, and emits the result as `LAT`/`LNG`. It is intentional —
do not strip it as noise. It blurs the exact point of a facility that may be a
real one, and it means successive reports from one device carry slightly
different coordinates, as a real GPS fix would. This matches the Python
implementation, which draws the same `gauss(0.00001, 0.001)` degree offset per
axis in `Facility.get_nudged_coordinates()`.

Three things follow:

- The offset is **not** anonymisation. 111 m is still inside the compound, so
  treat it as courtesy, not as a privacy control.
- It is **report-only**. `device.lat` / `device.lng` and the config you passed
  are never mutated, so anything rendering a fridge's position from your own
  data is unaffected — only the emitted report moves.
- It applies to **your** coordinates too. A facility read out of a `Catalogs`
  record and passed to `MonitoringDeviceConfig` goes through the same path, so
  reported coordinates will not match your registry exactly.

The jitter is drawn from the device's own `SeededRandom` stream, seeded from
`simConfig.random_seed`, so a seeded device stays fully deterministic. That
stream is deliberately separate from the one `SimulatedRecordSet.generate` uses
for measurements: emitting a coordinate never shifts a temperature. There is no
switch to turn the jitter off in either implementation.

### Stateful continuity

State persists between `generate()` calls via `SimulatorState`:

```javascript
const config = defaultConfig('mains', 12.0);
config.random_seed = 42;
const start = new Date(Date.UTC(2024, 0, 1));

// First batch
const rs1 = SimulatedRecordSet.generate(config, 96, start, 900);

// Continue from where we left off
const nextStart = new Date(start.getTime() + 96 * 900 * 1000);
const rs2 = SimulatedRecordSet.generate(config, 96, nextStart, 900, rs1.state);

// TVC is continuous across batches — no discontinuity
```

## Injecting anomalies

```javascript
import { defaultConfig, FaultType } from './src/index.js';

const config = defaultConfig('mains', 12.0);

// Compressor failure at hour 8, lasting 6 hours
config.fault.fault_type = FaultType.COMPRESSOR_FAILURE;
config.fault.fault_start_offset_s = 8 * 3600;
config.fault.fault_duration_s = 6 * 3600;
```

```javascript
// Refrigerant leak (permanent, gradual)
config.fault.fault_type = FaultType.REFRIGERANT_LEAK;
config.fault.fault_start_offset_s = 0;
config.fault.fault_duration_s = 0;
config.fault.refrigerant_leak_rate = 0.02;
```

### Door behavior presets

```javascript
import { EventConfig } from './src/index.js';

config.events = EventConfig.bestpractice();
config.events = EventConfig.normal();
config.events = EventConfig.fewButLong();     // causes HEAT alarms
config.events = EventConfig.frequentShort();
config.events = EventConfig.busyFacility();
```

Presets compose with faults:

```javascript
import { FaultConfig, FaultType, EventConfig } from './src/index.js';

config.events = EventConfig.fewButLong();
config.fault = new FaultConfig({
  fault_type: FaultType.POWER_OUTAGE,
  fault_start_offset_s: 3 * 86400,
  fault_duration_s: 24 * 3600,
});
```

## Catalogs

A catalog is a country's own list of facilities, appliances and loggers. **The
same files feed both implementations** — the field names inside a catalog file
are configuration, so they stay `snake_case` (and PQS-style `APQS`/`LMFR`) here
exactly as they are in Python, and no translation layer sits between the two.
The format itself — required fields, accepted key spellings, resolution order,
worked examples — is documented once, in [README_PYTHON.md](README_PYTHON.md).
This section covers only what the JavaScript port does differently.

### In the browser: `Catalogs.fromJSON()`

`Catalogs` lives in `js/src/catalogs.js`, which imports nothing at all — no
dependencies and no Node built-ins — so bundling `index.js` for a browser never
drags a filesystem module in behind it. It takes records already in hand:

```javascript
import { Catalogs } from './src/index.js';

// Records fetched, bundled, or built at runtime
const catalogs = new Catalogs({
  facilities: [{ iso: 'NGA', name: 'Example Central Hospital', lat: 13.06, lon: 5.25 }],
  appliances: [{ pqs_code: 'E003/040', manufacturer: 'Aucma', model: 'CFD-50', type: 'Icelined refrigerator' }],
});

catalogs.facilities[0].facility_name;  // 'Example Central Hospital' — keys normalized on load
catalogs.facilities[0].latitude;       // 13.06 — coordinates coerced to numbers
catalogs.loggers;                      // null — nothing supplied, nothing to fall back to
```

`Catalogs.fromJSON()` reads one bundled object instead — the shape to `fetch()`
a whole catalog as a single file. It is the three catalog arrays under their
kind names, plus the optional `manifest`:

```javascript
const response = await fetch('/catalog.json');
const catalogs = Catalogs.fromJSON(await response.text(), { source: 'catalog.json' });
```

`source` is only used in error messages; pass the filename so a bad record
names something the user can find.

### In Node: the `catalogs-node` subpath

Reading catalog *files* needs `fs`, which the browser-safe core will not
import. That lives in a separate module with its own export subpath, so it is
only loaded by code that asks for it:

```javascript
import { fromDir, fromFiles } from 'ems-data-simulator/catalogs-node';

const catalogs = fromDir('./ke-catalog');           // facilities/appliances/loggers.json
const facilities = fromFiles({ facilities: './hfr_export.json' });
```

`fromDir()` matches filenames case-insensitively, refuses two files claiming
the same catalog, and picks up a `manifest.json` beside them as
`catalogs.manifest`. Deliberately **not** re-exported from `index.js`.

### Two deliberate asymmetries with Python

**JSON only.** Python reads both `.json` and `.csv`, because a country's
facility list usually comes out of an HFR or OpenLMIS as a spreadsheet.
JavaScript reads `.json` and nothing else: parsing CSV correctly means a
runtime dependency, and `seedrandom` is the entire production budget. A `.csv`
catalog is reported as unsupported rather than skipped —

```
facilities.csv: .csv catalogs are not supported by the JavaScript port;
convert it to facilities.json (the Python implementation reads both)
```

— because silently loading someone else's facilities instead of your own is
the failure the loud loader exists to prevent. Convert the file once with the
Python side, or with any CSV-to-JSON tool; the JSON both ports then read is
identical.

**No packaged defaults.** Python falls back to catalogs packaged with the
`ccesim` distribution, so `Catalogs()` always holds all three kinds. The JS
port ships no facility or equipment data, so a kind that was not supplied stays
`null` (`catalogs.records(kind)` gives `[]` if you want a safe empty list).
Supply the kinds you need.

Everything else matches: keys are normalized on load, both spellings are
accepted (`APQS` and `pqs_code`, `LMFR` and `manufacturer`, `lat` and
`latitude`) along with case and spacing variants, unrecognized keys ride along
untouched so your own join columns survive, and validation is loud and happens
at load time, naming the file and the record:

```
./ke-catalog/facilities.json record 2: facility record is missing required
field 'latitude' (also accepted as 'lat')
```

`js/fixtures/catalog/` is a small catalog directory that both ports load and
agree on, record for record; it is what the cross-implementation parity test
reads.

### Feeding a device

Catalogs are not yet wired into `MonitoringDeviceConfig` — there is no
JavaScript equivalent of the Python `random_facility()` draw. Pick a record and
pass its fields:

```javascript
import { MonitoringDeviceConfig } from './src/index.js';

const facility = catalogs.facilities[0];
const appliance = catalogs.appliances[0];

const config = new MonitoringDeviceConfig({
  type: 'ems',
  uploadInterval: 3600,
  sampleInterval: 900,
  powerType: appliance.power_type ?? 'mains',
  amfr: appliance.AMFR,
  amod: appliance.AMOD,
  apqs: appliance.APQS,
  cid: facility.iso,
  lat: facility.latitude,
  lng: facility.longitude,
});
```

## Differences from the Python implementation

| Aspect | Python | JavaScript |
|--------|--------|------------|
| Schema validation | Pydantic 2.x | None (plain classes with `toJSON()`) |
| PRNG | Mersenne Twister (`random.Random`) | ARC4 (`seedrandom`) |
| Function naming | `snake_case` (`default_config`, `few_but_long`) | `camelCase` (`defaultConfig`, `fewButLong`) |
| Config field naming | `snake_case` | `snake_case` — deliberately kept, see below |
| Catalog format | JSON **and** CSV | JSON only — a CSV parser would be a new runtime dependency |
| Packaged catalogs | 7 illustrative facilities, 6 appliances, 3 loggers, plus the `nigeria-sokoto` and `pqs-e003-full` builtins | None shipped — supply the catalogs you need, or pass metadata per device |
| Catalog → device wiring | `MonitoringDeviceConfig` draws a facility, appliance and logger at random | Not yet — read a record from the catalog and pass its fields to `MonitoringDeviceConfig` yourself |
| Load testing | Locust integration | Not included |
| Notebooks | Jupyter examples with plots | Not included |

The physics engine, fault injection, alarm state machine, and CCE Data Delivery output formats are identical. Numerical outputs differ slightly due to the different PRNG algorithms, but behavioral characteristics match (verified by cross-validation tests).

## API reference

### Config classes

All config classes accept an options object in the constructor. Unspecified fields use defaults matching the Python implementation.

```javascript
new ThermalConfig({ R: 0.12, C: 48000, Q_compressor: 300 })
new AmbientConfig({ T_mean: 28, T_amplitude: 5 })
new PowerConfig({ power_type: 'solar', peak_dcsv: 48 })
new EventConfig({ door_rate_per_hour: 3.0 })
new FaultConfig({ fault_type: FaultType.STUCK_DOOR })
new SimulationConfig({ thermal, ambient, power, events, fault })
```

> **Why the field names are still `snake_case`.** Functions and methods in this
> port follow JS convention (`defaultConfig`, `fewButLong`), but *configuration
> field* names deliberately match the Python implementation character-for-character.
> Two reasons: several are physics notation rather than English words (`R`, `C`,
> `Q_compressor`, `T_setpoint_low`), and keeping them identical is what lets the
> cross-validation tests compare a JS config against a Python-generated fixture
> without a translation layer. Config objects are therefore portable between the
> two implementations as-is.

### `defaultConfig(powerType, latitude)`

Creates a complete `SimulationConfig` with sensible defaults. Ambient temperature is estimated from latitude.

### `SimulatedRecordSet.generate(config, batchSize, startTime, interval, state)`

- `config` — `SimulationConfig`
- `batchSize` — number of records to generate
- `startTime` — `Date` object (UTC)
- `interval` — seconds between samples (default 900)
- `state` — `SimulatorState` from a previous call (optional)

Returns a `SimulatedRecordSet` with `.records`, `.state`, `.toRtmd()`, `.toEms()`.

### `BaseRtmDevice`

```javascript
const device = new BaseRtmDevice(monitoringDeviceConfig);
const report = device.createReport(reportTime);  // RtmdReport or EmsReport
const json = report.toJSON();
```

### Schema classes

All schema classes have a `toJSON()` method that excludes undefined fields:

- `RtmdRecord` — ABST, BEMD, TVC, TAMB, ALRM, EERR
- `EmsRecordMains` — all EMS fields + SVA, ACCD, ACSV
- `EmsRecordSolar` — all EMS fields + DCSV, DCCD
- `RtmdReport` / `EmsReport` — metadata + records array
- `RtmdTransfer` / `EmsTransfer` — transfer envelope

### `SeededRandom`

Deterministic PRNG wrapper:

```javascript
import { SeededRandom } from './src/index.js';

const rng = new SeededRandom(42);
rng.random();           // uniform [0, 1)
rng.gauss(0, 1);        // Gaussian
rng.randint(1, 6);      // integer [1, 6]
rng.uniform(0, 10);     // float [0, 10]
rng.poisson(3.5);       // Poisson-distributed integer
rng.choice([1, 2, 3]);  // random element

// Save/restore state for simulation continuity
const state = rng.getState();
rng.setState(state);
```

## Project structure

```
js/
├── package.json
├── fixtures/
│   ├── generate_fixtures.py     Python script to regenerate reference data
│   ├── mains_normal.json        Reference fixture (24 records)
│   ├── solar_normal.json        Reference fixture (24 records)
│   ├── refrigerant_leak.json    Reference fixture (96 records)
│   ├── stuck_door.json          Reference fixture (24 records)
│   ├── power_outage.json        Reference fixture (24 records)
│   ├── compressor_failure.json  Reference fixture (24 records)
│   ├── icebank_unit.json        Reference fixture (96 records)
│   ├── busy_facility.json       Reference fixture (24 records)
│   └── catalog/                 Catalog directory both ports load (parity test)
└── src/
    ├── index.js                 Public API exports
    ├── config.js                Configuration classes + presets
    ├── thermal.js               RC thermal model, ambient model
    ├── power.js                 Mains and solar power models
    ├── events.js                Door generation, fault injection, alarms
    ├── recordset.js             Orchestration and schema conversion
    ├── schemas.js               cce-interop 0.8.1 output format classes
    ├── device.js                Device wrapper + report generation
    ├── random.js                Seedable PRNG wrapper
    ├── catalogs.js              Catalog loader (no imports — browser-safe)
    ├── catalogs-node.js         fromDir/fromFiles, the only module using fs
    ├── *.test.js                Unit tests (co-located)
    └── cross-validation.test.js Behavioral validation vs Python fixtures
```

## Running tests

```bash
cd js
npx vitest run        # all tests
npx vitest run src/thermal.test.js   # single module
npx vitest            # watch mode
```

### Regenerating cross-validation fixtures

If the Python implementation changes, regenerate the reference fixtures:

```bash
cd /path/to/ems-data-simulator
python3 js/fixtures/generate_fixtures.py
```

Then re-run the JS tests to verify behavioral equivalence.

### What cross-validation does *not* cover

Cross-validation compares **records** — the per-interval measurements a
`SimulatedRecordSet` produces — against Python-generated fixtures. The report
**envelope** is out of its scope today: `LAT`, `LNG`, `CID`, `AMID`, `ASER`,
`DLST` and the rest of the identity metadata are never generated into a fixture
(`js/fixtures/generate_fixtures.py` builds configs, never a device), so no
fixture can disagree about them and none does.

This is a real gap, recorded here rather than left silent — it is how the
coordinate-jitter divergence above survived unnoticed. Closing it is tracked as
beads issue `ccesim-bcp`. Until then, envelope parity between the two
implementations is held by each port's own unit tests, not by cross-validation.
