# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Nothing has been released yet: the Python distribution (`ccesim`) and the
JavaScript package (`ems-data-simulator`) are both at `0.1.0` and neither is
published to PyPI or npm, so there are no version tags and no release dates.
Everything below is unreleased work, newest concern first. History from before
the pre-publication pass is in `git log`.

Note that the **schema version emitted** (`cce-interop`) is versioned by the
specification, not by this project, and moves independently of these entries.

## [Unreleased]

### Changed

- **BREAKING (JavaScript consumers): the JS API is now camelCase.**
  `default_config()` → `defaultConfig()`, and the `EventConfig` presets
  `few_but_long()` / `frequent_short()` / `busy_facility()` →
  `fewButLong()` / `frequentShort()` / `busyFacility()`. This is a clean rename
  with **no back-compatibility aliases**, so existing callers must be updated.
  Config *field* names (`random_seed`, `fault_type`, `Q_compressor`, `R`, `C`)
  stay snake_case in both implementations on purpose — that is what lets the
  cross-validation fixtures be shared with no translation layer. The Python API
  is unchanged and remains snake_case.
- **BREAKING (Python consumers): the top-level package `utils` was renamed to
  `ccesim`.** Imports become `from ccesim.simulator import ...`. `utils` would
  have collided with anything else on the path once the project was installable,
  so the rename happened before publication rather than after.
- **The emitted schema version moved from `cce-interop` 0.8.0 to 0.8.1.** This is
  a conformance fix rather than a bare version bump: 0.8.1 widens `ACCD` to
  [0, 50] and tightens the `BLOG` maximum to 9999, and the simulator was already
  emitting `ACCD = 0` during a mains outage and already clamping `BLOG` to 9999.
  A mains-outage EMS transmission produced 16 validation errors against 0.8.0 and
  0 against 0.8.1. No simulator behaviour changed.
- The packaged default catalog is now a small illustrative sample (seven
  synthetic facilities, six appliances, three loggers), not a country-scale set.
  The full WHO PQS equipment catalogs remain available as builtins.
- Appliance records may declare `power_type` (`solar` or `mains`) explicitly,
  which now wins over sniffing the free-text type string. The sniff remains as a
  fallback and is logged; an unrecognised explicit value raises at load time,
  naming the appliance, instead of silently defaulting to mains.

### Added

- Pluggable facility, appliance and logger catalogs: point the simulator at a
  directory of JSON or CSV files and it draws devices from your own estate. A
  catalog with no file falls back to the packaged default. An optional
  `manifest.json` records where each catalog came from, with licence and
  citation.
- The Python side is installable: `pyproject.toml` declares the `ccesim`
  distribution, its runtime dependencies and its metadata, so `pip install -e .`
  works and `Pipfile` no longer restates dependencies.
- Continuous integration (`.github/workflows/ci.yml`): the Python suite, the
  JavaScript suite, the FHIR transform acceptance checks and the SUSHI FSH
  compile all run on push and on pull requests.
- FHIR R4 adoption work under `fhir/`: logical models, terminology, and a
  transform proof of concept that converts a generated EMS transmission to a
  validated FHIR Bundle, with alarms modelled as Observations plus DetectedIssue
  episodes.
- The beads issue database (`.beads/issues.jsonl`) is committed and published, so
  the project backlog is readable by anyone who clones the repo.
- `CCESIM_REQUIRE_FHIR=1` turns a missing `fhir.resources` install into a hard
  error instead of a module-level skip, so a stale environment can no longer make
  a partial run look green. CI sets it.

### Fixed

- The JavaScript port now jitters the reported facility coordinates the way the
  Python implementation does, from a device-local random stream that cannot shift
  a measurement. Previously it emitted the configured latitude and longitude
  verbatim, so the two implementations disagreed for the same facility.
- Catalog loading rejects duplicate CSV columns, accepts uppercase file
  extensions, and no longer trips over unnamed CSV columns.
- The Python and JavaScript catalog loaders are now held to the same reading of
  the same files.
- Documentation corrections: the JavaScript quick starts called a function that
  did not exist, catalog counts in the comparison table were overstated, and the
  spec links pointed at the CCDX routing layer rather than the CCE Data Delivery
  specification.

### Removed

- The defunct Azure SQL / ODBC export path, from `.env.example` and `Pipfile` —
  the code it configured was already gone.
- Internal issue-tracker IDs and device identifiers from all tracked files, along
  with references to a private calibration dataset and to internal design
  documents that are not published.
