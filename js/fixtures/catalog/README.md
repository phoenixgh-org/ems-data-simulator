# Parity catalog fixture

One catalog directory, read by BOTH implementations — `ccesim.catalogs.Catalogs.from_dir()`
in Python and `fromDir()` from `js/src/catalogs-node.js` in JavaScript. That is
the whole promise of the format: a country writes this once and both ports
agree on what they read.

The records are deliberately awkward, because the interesting behaviour is in
the normalization:

| Record | What it exercises |
|---|---|
| `facilities[0]` | Native keys, plus `local_cold_room_id` — an unrecognized key that must ride along untouched |
| `facilities[1]` | Short aliases: `iso3`, `name`, `lat`, `lon`, `facility_code` |
| `facilities[2]` | Spreadsheet headers: case and spacing variants, and coordinates as strings that must become numbers |
| `facilities[3]` | The other coordinate aliases: `lng`, `country_code`, `facility` |
| `appliances[0]` | PQS-style `APQS`/`AMFR`/`AMOD` |
| `appliances[1]` | Plain `pqs_code`/`manufacturer`/`model`, `power_source` value `"Solar"` lower-cased on load, plus unrecognized `asset_tag` |
| `appliances[2]` | Spreadsheet headers on an appliance, `"MAINS"` lower-cased on load |
| `loggers[0]` | PQS-style `LPQS`/`LMFR`/`LMOD` |
| `loggers[1]` | Plain keys, `device_type`, plus unrecognized `firmware_channel` |
| `loggers[2]` | A record mixing PQS-style and spreadsheet spellings |

`manifest.json` carries the fixture's provenance in the conventional shape.
Everything here is synthetic; the PQS codes are placeholders and prequalify
nothing.
