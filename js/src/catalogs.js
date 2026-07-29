/**
 * Pluggable facility and equipment catalogs — the browser-safe core.
 *
 * This is the JavaScript half of the catalog format documented for the Python
 * implementation in `ccesim/catalogs.py`. A country writes ONE catalog and both
 * ports read it: the field names inside a catalog file are configuration, so
 * they stay `snake_case` (and PQS-style `APQS`/`LMFR`) here exactly as they are
 * in Python, even though the JS *API* is camelCase.
 *
 *     new Catalogs({ facilities, appliances, loggers })   // arrays of objects
 *     Catalogs.fromJSON(text)                             // one bundled object
 *
 * THIS MODULE IMPORTS NOTHING. No Node built-ins, no dependencies — a browser
 * game bundling `index.js` must not drag a filesystem module in behind it. To
 * read catalogs off a disk from Node, import `ems-data-simulator/catalogs-node`,
 * which adds `fromDir()` / `fromFiles()` on top of this module.
 *
 * TWO DELIBERATE ASYMMETRIES WITH PYTHON:
 *
 *   1. JSON ONLY. Python also reads CSV; a CSV parser would be a new runtime
 *      dependency, and `seedrandom` is the whole production budget.
 *   2. NO PACKAGED DEFAULTS. Python falls back to catalogs packaged with the
 *      `ccesim` distribution; the JS port ships no facility or equipment data,
 *      so a catalog kind that is not supplied stays `null` rather than falling
 *      back. Supply the kinds you need.
 *
 * Everything else mirrors Python: key normalization, both accepted spellings,
 * unrecognized keys riding along untouched, loud validation at load time
 * naming the file and the row, and the optional provenance manifest.
 */

/** The three catalogs a Catalogs object carries. */
export const CATALOG_KINDS = Object.freeze([
  "facilities",
  "appliances",
  "loggers",
]);

/** Optional provenance file read from beside the catalog files. */
export const MANIFEST_FILENAME = "manifest.json";

/**
 * The provenance fields this project uses. A CONVENTION, NOT A SCHEMA: the
 * loader neither requires these nor rejects others, and never interprets a
 * value.
 */
export const MANIFEST_FIELDS = Object.freeze([
  "source",
  "vintage",
  "licence",
  "url",
  "retrieved",
  "citation",
]);

/** Power types an appliance record may declare. Mirrors `POWER_TYPES`. */
const POWER_TYPES = Object.freeze(["solar", "mains"]);

// ---------------------------------------------------------------------------
// Key normalization
// ---------------------------------------------------------------------------

/** Fold a source column name to the form the alias tables are keyed on. */
export function normalizeCatalogKey(key) {
  return String(key).trim().toLowerCase().replace(/ /g, "_").replace(/-/g, "_");
}

/**
 * The keys the Python `Facility` reads, verbatim. Listed so that an unmodified
 * NHFR-style export keeps every column, whatever its case or spacing.
 */
const FACILITY_NATIVE_KEYS = [
  "OBJECTID",
  "globalid",
  "nhfr_uid",
  "nhfr_facility_code",
  "country",
  "iso",
  "state",
  "lga",
  "lga_name_disagreement",
  "ward",
  "ward_name_disagreement",
  "facility_name",
  "facility_name_source",
  "ownership",
  "ownership_type",
  "facility_level",
  "facility_level_option",
  "latitude",
  "longitude",
  "geocoordinates_source",
  "last_updated",
];

/** Accepted facility key spellings, mapped to the stored form. */
export const FACILITY_ALIASES = Object.freeze(
  Object.assign(
    Object.fromEntries(
      FACILITY_NATIVE_KEYS.map((key) => [normalizeCatalogKey(key), key]),
    ),
    {
      lat: "latitude",
      lon: "longitude",
      lng: "longitude",
      long: "longitude",
      name: "facility_name",
      facility: "facility_name",
      iso3: "iso",
      iso_code: "iso",
      country_code: "iso",
      facility_code: "nhfr_facility_code",
    },
  ),
);

/** Accepted appliance key spellings, mapped to the stored form. */
export const APPLIANCE_ALIASES = Object.freeze({
  apqs: "APQS",
  pqs: "APQS",
  pqs_code: "APQS",
  amfr: "AMFR",
  manufacturer: "AMFR",
  amod: "AMOD",
  model: "AMOD",
  type: "type",
  appliance_type: "type",
  power_type: "power_type",
  powertype: "power_type",
  power_source: "power_type",
});

/** Accepted logger key spellings, mapped to the stored form. */
export const LOGGER_ALIASES = Object.freeze({
  lpqs: "LPQS",
  pqs: "LPQS",
  pqs_code: "LPQS",
  lmfr: "LMFR",
  manufacturer: "LMFR",
  lmod: "LMOD",
  model: "LMOD",
  type: "type",
  logger_type: "type",
  device_type: "type",
});

/**
 * Minimum required fields per kind, as [stored key, the plain equivalent an
 * error message should also mention].
 */
export const REQUIRED_FIELDS = Object.freeze({
  facilities: [
    ["iso", "iso"],
    ["latitude", "lat"],
    ["longitude", "lon"],
  ],
  appliances: [
    ["APQS", "pqs_code"],
    ["AMFR", "manufacturer"],
    ["AMOD", "model"],
    ["type", "type"],
  ],
  loggers: [
    ["LPQS", "pqs_code"],
    ["LMFR", "manufacturer"],
    ["LMOD", "model"],
    ["type", "type"],
  ],
});

/** Singular noun per kind, for error messages. */
const RECORD_NOUN = {
  facilities: "facility",
  appliances: "appliance",
  loggers: "logger",
};

// ---------------------------------------------------------------------------
// Small helpers for Python-shaped error messages
// ---------------------------------------------------------------------------

/** Quote a value the way Python's `repr()` would in an error message. */
function q(value) {
  if (typeof value === "string") return `'${value}'`;
  if (value === undefined) return "undefined";
  if (value === null) return "null";
  return String(value);
}

/** Name a value's type, for "expected X, got Y" messages. */
function typeName(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

/** True for a plain data object — the shape a catalog record must have. */
function isPlainObject(value) {
  return (
    value !== null && typeof value === "object" && !Array.isArray(value)
  );
}

/** Build a human-readable label for a catalog record, for error messages. */
function deviceLabel(record) {
  const pqs = record.APQS || record.LPQS || "?";
  const manufacturer = record.AMFR || record.LMFR || "?";
  const model = record.AMOD || record.LMOD || "?";
  return `${pqs} (${manufacturer} ${model})`;
}

// ---------------------------------------------------------------------------
// Normalization and validation
// ---------------------------------------------------------------------------

/**
 * Rename a record's recognized keys to their stored form, leaving everything
 * else exactly as the user wrote it.
 */
function normalizeRecord(record, aliases, location) {
  const normalized = {};
  const origin = {};
  for (const [key, value] of Object.entries(record)) {
    const stored = aliases[normalizeCatalogKey(key)] ?? key;
    if (stored in origin && origin[stored] !== key) {
      throw new Error(
        `${location}: ${q(origin[stored])} and ${q(key)} both mean ` +
          `${q(stored)}; keep only one of them`,
      );
    }
    normalized[stored] = value;
    origin[stored] = key;
  }
  return normalized;
}

function requireFields(record, kind, location) {
  const noun = RECORD_NOUN[kind];
  for (const [stored, plain] of REQUIRED_FIELDS[kind]) {
    const value = record[stored];
    const blank =
      value === undefined ||
      value === null ||
      (typeof value === "string" && value.trim() === "");
    if (blank) {
      const also = plain === stored ? "" : ` (also accepted as ${q(plain)})`;
      throw new Error(
        `${location}: ${noun} record is missing required field ` +
          `${q(stored)}${also}`,
      );
    }
  }
}

/**
 * Turn a coordinate into a number and sanity-check its range. A latitude that
 * stays a string -- or that lost its decimal point -- reaches the ambient and
 * solar models as nonsense.
 */
function coerceCoordinate(record, field, limit, location) {
  const value = record[field];
  const numeric =
    typeof value === "number" || typeof value === "string"
      ? Number(value)
      : NaN;
  if (typeof value === "string" && value.trim() === "") {
    throw new Error(`${location}: facility ${field} ${q(value)} is not a number`);
  }
  if (Number.isNaN(numeric)) {
    throw new Error(`${location}: facility ${field} ${q(value)} is not a number`);
  }
  if (!(numeric >= -limit && numeric <= limit)) {
    throw new Error(
      `${location}: facility ${field} ${numeric} is outside ${-limit}..${limit}`,
    );
  }
  record[field] = numeric;
}

/**
 * Normalize and validate an explicit power_type value. An unrecognized power
 * type must never fall through to a default, because the power type selects
 * the entire physical model of the appliance.
 */
function validatePowerType(powerType, label, location) {
  if (powerType === null || powerType === undefined) return null;
  const normalized =
    typeof powerType === "string" ? powerType.trim().toLowerCase() : powerType;
  if (!POWER_TYPES.includes(normalized)) {
    throw new Error(
      `${location}: Invalid power_type ${q(powerType)} for appliance ${label}: ` +
        `expected one of ${POWER_TYPES.map(q).join(", ")}`,
    );
  }
  return normalized;
}

function validateFacility(record, location) {
  requireFields(record, "facilities", location);
  coerceCoordinate(record, "latitude", 90, location);
  coerceCoordinate(record, "longitude", 180, location);
}

function validateAppliance(record, location) {
  requireFields(record, "appliances", location);
  if ("power_type" in record) {
    record.power_type = validatePowerType(
      record.power_type,
      deviceLabel(record),
      location,
    );
  }
}

function validateLogger(record, location) {
  requireFields(record, "loggers", location);
}

const KIND_HANDLERS = {
  facilities: [FACILITY_ALIASES, validateFacility],
  appliances: [APPLIANCE_ALIASES, validateAppliance],
  loggers: [LOGGER_ALIASES, validateLogger],
};

// ---------------------------------------------------------------------------
// Provenance manifests
// ---------------------------------------------------------------------------

/**
 * Check a manifest's SHAPE -- keyed by catalog kind, each entry an object --
 * and copy it. The fields inside an entry are never inspected: they are for a
 * human, and a country that wants to record its own extra terms should be able
 * to.
 */
export function validateManifest(manifest, location) {
  if (!isPlainObject(manifest)) {
    throw new TypeError(
      `${location}: manifest must be an object keyed by catalog kind ` +
        `(${CATALOG_KINDS.join(", ")}), got ${typeName(manifest)}`,
    );
  }
  const validated = {};
  for (const [kind, entry] of Object.entries(manifest)) {
    if (!CATALOG_KINDS.includes(kind)) {
      throw new Error(
        `${location}: ${q(kind)} is not a catalog kind; a manifest is keyed ` +
          `by ${CATALOG_KINDS.join(", ")}, and each of those holds the ` +
          `provenance fields (${MANIFEST_FIELDS.join(", ")})`,
      );
    }
    if (!isPlainObject(entry)) {
      throw new Error(
        `${location}: ${q(kind)} provenance must be an object of fields, got ` +
          `${typeName(entry)}`,
      );
    }
    validated[kind] = { ...entry };
  }
  return validated;
}

/**
 * Work out the provenance of the catalogs this object ends up holding.
 *
 * Unlike Python there are no packaged catalogs to inherit provenance from, so
 * a manifest entry describing a kind that was not supplied is an error rather
 * than a claim about the packaged default.
 */
function resolveManifest(manifest, supplied) {
  const location = "manifest passed to Catalogs()";
  if (manifest === null || manifest === undefined) return {};
  const given = validateManifest(manifest, location);
  for (const kind of Object.keys(given)) {
    if (supplied[kind] === null || supplied[kind] === undefined) {
      throw new Error(
        `${location}: it describes ${q(kind)}, but no ${kind} catalog was ` +
          `supplied; supply the ${kind} catalog or drop the entry`,
      );
    }
  }
  return given;
}

// ---------------------------------------------------------------------------
// Catalogs
// ---------------------------------------------------------------------------

/** Normalize and validate every record of one catalog. */
function prepare(records, kind, source) {
  if (!Array.isArray(records)) {
    throw new TypeError(
      `${kind} must be an array of objects, got ${typeName(records)}; use ` +
        `the catalogs-node module to load them from a path`,
    );
  }
  const [aliases, validate] = KIND_HANDLERS[kind];
  const prepared = [];
  records.forEach((raw, index) => {
    const location = `${source} record ${index + 1}`;
    if (!isPlainObject(raw)) {
      throw new TypeError(
        `${location}: expected an object, got ${typeName(raw)}`,
      );
    }
    const record = normalizeRecord(raw, aliases, location);
    validate(record, location);
    prepared.push(record);
  });
  if (prepared.length === 0) {
    throw new Error(`${source}: ${kind} catalog is empty`);
  }
  return prepared;
}

/**
 * The three catalogs the simulator draws from: facilities, appliances and
 * loggers.
 *
 * Each argument is an array of plain objects. Records are normalized and
 * validated on the way in, so a Catalogs object that exists is one every
 * consumer can read without re-checking. The arrays are copies -- loading
 * never mutates the objects handed in.
 *
 * A kind that is not supplied is `null`: the JS port ships no packaged
 * catalogs to fall back to (see the module docstring).
 *
 * `manifest` is optional provenance keyed by catalog kind, exposed as
 * `.manifest` -- an empty object when none was given. `sources` names where
 * each kind came from, and is what makes a validation failure quote a filename
 * and a record number; the catalogs-node wrapper fills it in with real paths.
 */
export class Catalogs {
  constructor({
    facilities = null,
    appliances = null,
    loggers = null,
    manifest = null,
    sources = null,
  } = {}) {
    const supplied = { facilities, appliances, loggers };
    for (const kind of CATALOG_KINDS) {
      const records = supplied[kind];
      if (records === null || records === undefined) {
        this[kind] = null;
        continue;
      }
      const source =
        (sources && sources[kind]) || `${kind} passed to Catalogs()`;
      this[kind] = prepare(records, kind, source);
    }
    this.manifest = resolveManifest(manifest, supplied);
  }

  /**
   * Load catalogs from one JSON bundle -- the browser's route in, where there
   * is no directory to walk.
   *
   *     Catalogs.fromJSON(await (await fetch('catalog.json')).text())
   *
   * The bundle is an object keyed by catalog kind, each holding the same array
   * of records a `facilities.json` file holds, plus an optional `manifest`
   * with the contents of a `manifest.json`.
   *
   * @param {string|object} input - JSON text, or the already-parsed object.
   * @param {object} [options]
   * @param {string} [options.source] - Name used in error messages.
   */
  static fromJSON(input, { source = "catalog JSON" } = {}) {
    let payload = input;
    if (typeof payload === "string") {
      try {
        payload = JSON.parse(payload);
      } catch (error) {
        throw new Error(`${source}: not valid JSON: ${error.message}`);
      }
    }
    if (!isPlainObject(payload)) {
      throw new TypeError(
        `${source}: expected an object keyed by catalog kind ` +
          `(${CATALOG_KINDS.join(", ")}), got ${typeName(payload)}`,
      );
    }
    const options = { manifest: payload.manifest ?? null, sources: {} };
    for (const key of Object.keys(payload)) {
      if (key !== "manifest" && !CATALOG_KINDS.includes(key)) {
        throw new Error(
          `${source}: ${q(key)} is not a catalog kind; expected any of ` +
            `${CATALOG_KINDS.join(", ")} or ${q("manifest")}`,
        );
      }
    }
    for (const kind of CATALOG_KINDS) {
      if (payload[kind] === undefined) continue;
      options[kind] = payload[kind];
      options.sources[kind] = `${source} (${kind})`;
    }
    return new Catalogs(options);
  }

  /** Records of one kind, or `[]` when that kind was not supplied. */
  records(kind) {
    if (!CATALOG_KINDS.includes(kind)) {
      throw new Error(
        `${q(kind)} is not a catalog kind; expected any of ` +
          `${CATALOG_KINDS.join(", ")}`,
      );
    }
    return this[kind] ?? [];
  }

  toString() {
    const count = (kind) => (this[kind] === null ? "none" : this[kind].length);
    return (
      `Catalogs(facilities=${count("facilities")}, ` +
      `appliances=${count("appliances")}, loggers=${count("loggers")})`
    );
  }
}
