/**
 * Catalog loader tests.
 *
 * These mirror the guarantees `tests/test_catalogs.py` pins on the Python
 * loader: keys are normalized on load, both spellings are accepted,
 * unrecognized keys ride along untouched, and validation is loud and names the
 * file and the row. The cross-implementation agreement itself is asserted in
 * cross-validation.test.js against js/fixtures/catalog/.
 */

import { describe, it, expect } from "vitest";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  Catalogs,
  CATALOG_KINDS,
  FACILITY_ALIASES,
  APPLIANCE_ALIASES,
  LOGGER_ALIASES,
  normalizeCatalogKey,
} from "./index.js";
import { fromDir, fromFiles } from "./catalogs-node.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const CATALOG_FIXTURE = join(__dirname, "..", "fixtures", "catalog");

const FACILITY = {
  iso: "NGA",
  facility_name: "Example Central Hospital",
  latitude: 13.06,
  longitude: 5.25,
};
const APPLIANCE = {
  APQS: "E003/000-EXAMPLE-1",
  AMFR: "Example Cold Chain Co",
  AMOD: "EX-100",
  type: "Icelined refrigerator",
};
const LOGGER = {
  LPQS: "E006/000-EXAMPLE-1",
  LMFR: "Example Telemetry Ltd",
  LMOD: "LX-10",
  type: "Remote temperature monitoring device",
};

// ---------------------------------------------------------------------------
// The pure core
// ---------------------------------------------------------------------------

describe("Catalogs (in-memory)", () => {
  it("loads records handed in directly", () => {
    const catalogs = new Catalogs({
      facilities: [FACILITY],
      appliances: [APPLIANCE],
      loggers: [LOGGER],
    });
    expect(catalogs.facilities).toHaveLength(1);
    expect(catalogs.appliances).toHaveLength(1);
    expect(catalogs.loggers).toHaveLength(1);
  });

  it("leaves a kind that was not supplied null", () => {
    const catalogs = new Catalogs({ facilities: [FACILITY] });
    expect(catalogs.appliances).toBeNull();
    expect(catalogs.loggers).toBeNull();
    expect(catalogs.records("loggers")).toEqual([]);
  });

  it("never mutates the objects handed in", () => {
    const raw = { iso: "NGA", lat: "13.06", lon: "5.25" };
    new Catalogs({ facilities: [raw] });
    expect(raw).toEqual({ iso: "NGA", lat: "13.06", lon: "5.25" });
  });

  it("rejects a catalog that is not an array", () => {
    expect(() => new Catalogs({ facilities: FACILITY })).toThrow(
      /facilities must be an array of objects/,
    );
  });

  it("rejects a record that is not an object", () => {
    expect(() => new Catalogs({ facilities: ["Sokoto"] })).toThrow(
      /record 1: expected an object, got string/,
    );
  });

  it("rejects an empty catalog", () => {
    expect(() => new Catalogs({ loggers: [] })).toThrow(
      /loggers catalog is empty/,
    );
  });

  it("reports its contents", () => {
    const catalogs = new Catalogs({ facilities: [FACILITY] });
    expect(String(catalogs)).toBe(
      "Catalogs(facilities=1, appliances=none, loggers=none)",
    );
  });
});

// ---------------------------------------------------------------------------
// Key normalization
// ---------------------------------------------------------------------------

describe("key normalization", () => {
  it("folds case, spaces and dashes", () => {
    expect(normalizeCatalogKey(" Facility-Name ")).toBe("facility_name");
    expect(normalizeCatalogKey("ISO Code")).toBe("iso_code");
  });

  it("accepts the short facility aliases", () => {
    const catalogs = new Catalogs({
      facilities: [
        { iso3: "KEN", name: "Example Hospital", lat: -1.29, lng: 36.82 },
      ],
    });
    expect(catalogs.facilities[0]).toEqual({
      iso: "KEN",
      facility_name: "Example Hospital",
      latitude: -1.29,
      longitude: 36.82,
    });
  });

  it("accepts plain appliance keys and stores them PQS-style", () => {
    const catalogs = new Catalogs({
      appliances: [
        {
          pqs_code: "E003/000-EXAMPLE-2",
          manufacturer: "Example Solar Systems",
          model: "EX-S200",
          appliance_type: "Solar direct drive refrigerator",
        },
      ],
    });
    expect(Object.keys(catalogs.appliances[0]).sort()).toEqual([
      "AMFR",
      "AMOD",
      "APQS",
      "type",
    ]);
  });

  it("accepts plain logger keys and stores them PQS-style", () => {
    const catalogs = new Catalogs({
      loggers: [
        {
          pqs_code: "E006/000-EXAMPLE-2",
          manufacturer: "Example Telemetry Ltd",
          model: "LX-20",
          device_type: "Remote temperature monitoring device",
        },
      ],
    });
    expect(Object.keys(catalogs.loggers[0]).sort()).toEqual([
      "LMFR",
      "LMOD",
      "LPQS",
      "type",
    ]);
  });

  it("produces the same record from PQS-keyed and plain-keyed input", () => {
    const pqs = new Catalogs({ appliances: [APPLIANCE] });
    const plain = new Catalogs({
      appliances: [
        {
          pqs_code: APPLIANCE.APQS,
          manufacturer: APPLIANCE.AMFR,
          model: APPLIANCE.AMOD,
          type: APPLIANCE.type,
        },
      ],
    });
    expect(plain.appliances[0]).toEqual(pqs.appliances[0]);
  });

  it("accepts spreadsheet-style headers", () => {
    const catalogs = new Catalogs({
      facilities: [
        {
          "ISO Code": "ETH",
          "Facility Name": "Example Woreda Health Centre",
          Latitude: "9.03",
          LONGITUDE: "38.74",
        },
      ],
    });
    expect(catalogs.facilities[0]).toEqual({
      iso: "ETH",
      facility_name: "Example Woreda Health Centre",
      latitude: 9.03,
      longitude: 38.74,
    });
  });

  it("leaves unrecognized keys untouched", () => {
    const catalogs = new Catalogs({
      facilities: [{ ...FACILITY, local_cold_room_id: "CR-001" }],
    });
    expect(catalogs.facilities[0].local_cold_room_id).toBe("CR-001");
  });

  it("rejects two keys that mean the same field", () => {
    expect(
      () =>
        new Catalogs({
          facilities: [{ iso: "NGA", lat: 13.06, latitude: 13.5, lon: 5.25 }],
        }),
    ).toThrow(/both mean 'latitude'; keep only one of them/);
  });

  it("keeps distinct keys that merely look alike", () => {
    const catalogs = new Catalogs({
      facilities: [{ ...FACILITY, latitude_source: "GPS" }],
    });
    expect(catalogs.facilities[0].latitude_source).toBe("GPS");
    expect(catalogs.facilities[0].latitude).toBe(13.06);
  });

  it("keeps the alias tables in step with Python", () => {
    // Spot-checks of the tables ccesim/catalogs.py defines; the full
    // agreement is asserted by the cross-implementation parity test.
    expect(FACILITY_ALIASES.long).toBe("longitude");
    expect(FACILITY_ALIASES.country_code).toBe("iso");
    expect(APPLIANCE_ALIASES.pqs).toBe("APQS");
    expect(APPLIANCE_ALIASES.powertype).toBe("power_type");
    expect(LOGGER_ALIASES.pqs).toBe("LPQS");
    expect(LOGGER_ALIASES.logger_type).toBe("type");
    expect(CATALOG_KINDS).toEqual(["facilities", "appliances", "loggers"]);
  });
});

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

describe("validation", () => {
  it("names the file and the record when a latitude is missing", () => {
    const path = join(CATALOG_FIXTURE, "facilities.json");
    const records = JSON.parse(readFileSync(path, "utf-8"));
    delete records[1].lat;
    expect(() =>
      new Catalogs({ facilities: records, sources: { facilities: path } }),
    ).toThrow(/facilities\.json record 2: facility record is missing required field 'latitude' \(also accepted as 'lat'\)/);
  });

  it("treats a blank string as missing", () => {
    expect(
      () => new Catalogs({ facilities: [{ ...FACILITY, iso: "  " }] }),
    ).toThrow(/missing required field 'iso'/);
  });

  it("rejects a non-numeric latitude", () => {
    expect(
      () => new Catalogs({ facilities: [{ ...FACILITY, latitude: "13,06" }] }),
    ).toThrow(/facility latitude '13,06' is not a number/);
  });

  it("rejects an out-of-range latitude", () => {
    expect(
      () => new Catalogs({ facilities: [{ ...FACILITY, latitude: 130.6 }] }),
    ).toThrow(/facility latitude 130\.6 is outside -90\.\.90/);
  });

  it("allows a longitude beyond ninety", () => {
    const catalogs = new Catalogs({
      facilities: [{ ...FACILITY, longitude: 140.2 }],
    });
    expect(catalogs.facilities[0].longitude).toBe(140.2);
  });

  it("turns string coordinates into numbers", () => {
    const catalogs = new Catalogs({
      facilities: [{ iso: "ETH", lat: "9.03", lon: "38.74" }],
    });
    expect(catalogs.facilities[0].latitude).toBe(9.03);
    expect(catalogs.facilities[0].longitude).toBe(38.74);
  });

  it("rejects an appliance with no model", () => {
    const { AMOD, ...rest } = APPLIANCE;
    expect(() => new Catalogs({ appliances: [rest] })).toThrow(
      /missing required field 'AMOD' \(also accepted as 'model'\)/,
    );
  });

  it("rejects a logger with no type", () => {
    const { type, ...rest } = LOGGER;
    expect(() => new Catalogs({ loggers: [rest] })).toThrow(
      /logger record is missing required field 'type'/,
    );
  });

  it("fails loudly when an appliance list is loaded as loggers", () => {
    expect(() => new Catalogs({ loggers: [APPLIANCE] })).toThrow(
      /missing required field 'LPQS'/,
    );
  });

  it("normalizes a declared power type", () => {
    const catalogs = new Catalogs({
      appliances: [{ ...APPLIANCE, power_source: " Solar " }],
    });
    expect(catalogs.appliances[0].power_type).toBe("solar");
  });

  it("rejects an unrecognized power type", () => {
    expect(
      () => new Catalogs({ appliances: [{ ...APPLIANCE, power_type: "gas" }] }),
    ).toThrow(/Invalid power_type 'gas' for appliance E003\/000-EXAMPLE-1/);
  });
});

// ---------------------------------------------------------------------------
// fromJSON — the browser's route in
// ---------------------------------------------------------------------------

describe("Catalogs.fromJSON", () => {
  const bundle = {
    facilities: [FACILITY],
    appliances: [APPLIANCE],
    loggers: [LOGGER],
  };

  it("accepts JSON text", () => {
    const catalogs = Catalogs.fromJSON(JSON.stringify(bundle));
    expect(catalogs.facilities[0].facility_name).toBe(
      "Example Central Hospital",
    );
  });

  it("accepts an already-parsed object", () => {
    expect(Catalogs.fromJSON(bundle).loggers).toHaveLength(1);
  });

  it("names the source in a validation failure", () => {
    expect(() =>
      Catalogs.fromJSON(
        { facilities: [{ iso: "NGA", lon: 5.25 }] },
        { source: "catalog.json" },
      ),
    ).toThrow(/catalog\.json \(facilities\) record 1: .*'latitude'/);
  });

  it("reports malformed JSON", () => {
    expect(() => Catalogs.fromJSON("{oops")).toThrow(/not valid JSON/);
  });

  it("rejects a bare array, which names no kind", () => {
    expect(() => Catalogs.fromJSON("[]")).toThrow(
      /expected an object keyed by catalog kind/,
    );
  });

  it("rejects a key that is not a catalog kind", () => {
    expect(() => Catalogs.fromJSON({ fridges: [] })).toThrow(
      /'fridges' is not a catalog kind/,
    );
  });

  it("carries a manifest through", () => {
    const catalogs = Catalogs.fromJSON({
      ...bundle,
      manifest: { facilities: { source: "Kenya MFL", licence: "CC BY 4.0" } },
    });
    expect(catalogs.manifest.facilities.licence).toBe("CC BY 4.0");
  });
});

// ---------------------------------------------------------------------------
// Manifests
// ---------------------------------------------------------------------------

describe("manifests", () => {
  it("defaults to no provenance", () => {
    expect(new Catalogs({ facilities: [FACILITY] }).manifest).toEqual({});
  });

  it("rejects a manifest key that is not a catalog kind", () => {
    expect(
      () =>
        new Catalogs({
          facilities: [FACILITY],
          manifest: { fridges: { source: "?" } },
        }),
    ).toThrow(/'fridges' is not a catalog kind/);
  });

  it("rejects a manifest entry that is not an object", () => {
    expect(
      () =>
        new Catalogs({
          facilities: [FACILITY],
          manifest: { facilities: "Kenya MFL" },
        }),
    ).toThrow(/provenance must be an object of fields, got string/);
  });

  it("rejects provenance for a catalog that was not supplied", () => {
    expect(
      () =>
        new Catalogs({
          facilities: [FACILITY],
          manifest: { loggers: { source: "?" } },
        }),
    ).toThrow(/no loggers catalog was supplied/);
  });

  it("leaves the manifest fields free-form", () => {
    const catalogs = new Catalogs({
      facilities: [FACILITY],
      manifest: { facilities: { source: "MFL", ward_note: "hand-checked" } },
    });
    expect(catalogs.manifest.facilities.ward_note).toBe("hand-checked");
  });
});

// ---------------------------------------------------------------------------
// The Node wrapper
// ---------------------------------------------------------------------------

describe("catalogs-node", () => {
  it("loads the shared parity fixture directory", () => {
    const catalogs = fromDir(CATALOG_FIXTURE);
    expect(catalogs.facilities).toHaveLength(4);
    expect(catalogs.appliances).toHaveLength(3);
    expect(catalogs.loggers).toHaveLength(3);
    expect(catalogs.manifest.facilities.licence).toBe(
      "MIT, as part of this package",
    );
  });

  it("normalizes every spelling in the fixture to one stored form", () => {
    const catalogs = fromDir(CATALOG_FIXTURE);
    expect(catalogs.facilities.map((f) => f.iso)).toEqual([
      "NGA",
      "KEN",
      "ETH",
      "ZAF",
    ]);
    for (const facility of catalogs.facilities) {
      expect(typeof facility.latitude).toBe("number");
      expect(typeof facility.longitude).toBe("number");
      expect(facility.facility_name).toMatch(/^Example /);
    }
    expect(catalogs.appliances.map((a) => a.APQS)).toEqual([
      "E003/000-EXAMPLE-1",
      "E003/000-EXAMPLE-2",
      "E003/000-EXAMPLE-3",
    ]);
    expect(catalogs.appliances.map((a) => a.power_type)).toEqual([
      "mains",
      "solar",
      "mains",
    ]);
    expect(catalogs.loggers.map((l) => l.LMFR)).toEqual([
      "Example Telemetry Ltd",
      "Example Telemetry Ltd",
      "Example Sensors Inc",
    ]);
  });

  it("keeps the fixture's unrecognized keys", () => {
    const catalogs = fromDir(CATALOG_FIXTURE);
    expect(catalogs.facilities[0].local_cold_room_id).toBe("CR-001");
    expect(catalogs.appliances[1].asset_tag).toBe("AST-77");
    expect(catalogs.loggers[1].firmware_channel).toBe("stable");
  });

  it("loads one file at a time", () => {
    const catalogs = fromFiles({
      facilities: join(CATALOG_FIXTURE, "facilities.json"),
    });
    expect(catalogs.facilities).toHaveLength(4);
    expect(catalogs.appliances).toBeNull();
  });

  it("needs at least one file", () => {
    expect(() => fromFiles({})).toThrow(/needs at least one of/);
  });

  it("names a missing file", () => {
    expect(() => fromFiles({ loggers: "/no/such/loggers.json" })).toThrow(
      /no such loggers catalog file/,
    );
  });

  it("rejects a directory that is not there", () => {
    expect(() => fromDir("/no/such/catalog")).toThrow(
      /not a catalog directory/,
    );
  });

  it("names the file and the record when the file is bad", () => {
    expect(() =>
      fromFiles({ appliances: join(CATALOG_FIXTURE, "manifest.json") }),
    ).toThrow(/manifest\.json: expected a JSON array of appliances records/);
  });

  it("reports CSV as unsupported rather than ignoring it", () => {
    const dir = mkdtempSync(join(tmpdir(), "ccesim-catalog-"));
    const path = join(dir, "facilities.csv");
    writeFileSync(path, "iso,latitude,longitude\nNGA,13.06,5.25\n");
    // Both routes in, because silently skipping a country's own facility
    // list is exactly the failure the loud loader exists to prevent.
    expect(() => fromFiles({ facilities: path })).toThrow(
      /\.csv catalogs are not supported by the JavaScript port/,
    );
    expect(() => fromDir(dir)).toThrow(
      /\.csv catalogs are not supported by the JavaScript port/,
    );
  });

  it("rejects a directory with no catalog files", () => {
    const dir = mkdtempSync(join(tmpdir(), "ccesim-catalog-"));
    writeFileSync(join(dir, "notes.txt"), "nothing to see");
    expect(() => fromDir(dir)).toThrow(/no catalog files found/);
  });

  it("finds an uppercase filename and extension", () => {
    const dir = mkdtempSync(join(tmpdir(), "ccesim-catalog-"));
    writeFileSync(join(dir, "Facilities.JSON"), JSON.stringify([FACILITY]));
    expect(fromDir(dir).facilities).toHaveLength(1);
  });

  it("refuses two files claiming the same catalog", () => {
    const dir = mkdtempSync(join(tmpdir(), "ccesim-catalog-"));
    writeFileSync(join(dir, "facilities.json"), JSON.stringify([FACILITY]));
    writeFileSync(join(dir, "Facilities.json"), JSON.stringify([FACILITY]));
    expect(() => fromDir(dir)).toThrow(/found more than one facilities catalog file/);
  });

  it("refuses a manifest describing a catalog the directory does not have", () => {
    const dir = mkdtempSync(join(tmpdir(), "ccesim-catalog-"));
    writeFileSync(join(dir, "facilities.json"), JSON.stringify([FACILITY]));
    writeFileSync(
      join(dir, "manifest.json"),
      JSON.stringify({ loggers: { source: "?" } }),
    );
    expect(() => fromDir(dir)).toThrow(
      /describes 'loggers', but the directory has no loggers catalog file/,
    );
  });
});

// ---------------------------------------------------------------------------
// The browser-safe boundary
// ---------------------------------------------------------------------------

describe("the browser-safe boundary", () => {
  it("keeps Node built-ins out of the pure catalog module", () => {
    // Deliberately the same crude check the bite states as its acceptance
    // criterion: the string must not appear in catalogs.js at all, comments
    // included, so that grepping js/src for it finds only catalogs-node.js.
    const source = readFileSync(join(__dirname, "catalogs.js"), "utf-8");
    expect(source).not.toContain("node:");
    expect(source).not.toMatch(/^import /m);
  });

  it("does not export the Node wrapper from index.js", async () => {
    const api = await import("./index.js");
    expect(api.Catalogs).toBeDefined();
    expect(api.fromDir).toBeUndefined();
  });
});
