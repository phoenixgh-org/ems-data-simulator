import { describe, it, expect } from "vitest";
import {
  MonitoringDeviceConfig,
  BaseRtmDevice,
  randomSerial,
  transferMetadata,
} from "./device.js";
import {
  RtmdReport,
  EmsReport,
  RtmdRecord,
  TransferMetadata,
  SCHEMA_VERSION,
  TRANSFER_SRC,
} from "./schemas.js";
import { defaultConfig } from "./config.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeConfig(overrides = {}) {
  return new MonitoringDeviceConfig({
    type: "rtmd",
    uploadInterval: 3600,
    sampleInterval: 900,
    powerType: "mains",
    amfr: "Vestfrost",
    amod: "VLS-054",
    apqs: "E003/034",
    cid: "KEN",
    lat: -1.3,
    lng: 36.8,
    lmfr: "B Medical",
    lmod: "WT-100",
    lpqs: "E006/001",
    ...overrides,
  });
}

function makeEmsConfig(overrides = {}) {
  return new MonitoringDeviceConfig({
    type: "ems",
    uploadInterval: 3600,
    sampleInterval: 900,
    powerType: "mains",
    amfr: "Haier",
    amod: "HBC-200",
    apqs: "E003/100",
    cid: "NGA",
    lat: 9.0,
    lng: 7.5,
    ...overrides,
  });
}

const REPORT_TIME = new Date("2024-06-15T12:00:00Z");

// ---------------------------------------------------------------------------
// MonitoringDeviceConfig
// ---------------------------------------------------------------------------

describe("MonitoringDeviceConfig", () => {
  it("derives batchSize from uploadInterval / sampleInterval", () => {
    const cfg = makeConfig();
    expect(cfg.batchSize).toBe(4); // 3600 / 900
  });

  it("derives batchSize for different intervals", () => {
    const cfg = makeConfig({ uploadInterval: 7200, sampleInterval: 600 });
    expect(cfg.batchSize).toBe(12);
  });

  it("throws when uploadInterval < sampleInterval", () => {
    expect(() => makeConfig({ uploadInterval: 300, sampleInterval: 900 })).toThrow();
  });

  it("throws when uploadInterval is not a multiple of sampleInterval", () => {
    expect(() => makeConfig({ uploadInterval: 1000, sampleInterval: 900 })).toThrow();
  });

  it("throws for invalid type", () => {
    expect(() => makeConfig({ type: "foo" })).toThrow();
  });

  it("stores all metadata fields", () => {
    const cfg = makeConfig();
    expect(cfg.type).toBe("rtmd");
    expect(cfg.amfr).toBe("Vestfrost");
    expect(cfg.amod).toBe("VLS-054");
    expect(cfg.apqs).toBe("E003/034");
    expect(cfg.cid).toBe("KEN");
    expect(cfg.lat).toBe(-1.3);
    expect(cfg.lng).toBe(36.8);
    expect(cfg.lmfr).toBe("B Medical");
    expect(cfg.lmod).toBe("WT-100");
  });

  it("uses default simConfig when not provided", () => {
    const cfg = makeConfig();
    expect(cfg.simConfig).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// BaseRtmDevice — RTMD
// ---------------------------------------------------------------------------

describe("BaseRtmDevice (RTMD)", () => {
  it("initializes with correct metadata", () => {
    const dev = new BaseRtmDevice(makeConfig());
    expect(dev.amfr).toBe("Vestfrost");
    expect(dev.amod).toBe("VLS-054");
    expect(dev.cid).toBe("KEN");
    expect(dev.simulatorState).toBeNull();
    // RTMD: logger has its own identity
    expect(dev.lmfr).toBe("B Medical");
    expect(dev.lmod).toBe("WT-100");
  });

  it("auto-generates aser and lser when not provided", () => {
    const dev = new BaseRtmDevice(makeConfig());
    expect(dev.aser).toMatch(/^[0-9a-f]{32}$/);
    expect(dev.lser).toMatch(/^[0-9a-f]{32}$/);
    expect(dev.aser).not.toBe(dev.lser);
  });

  it("createReport returns an RtmdReport with correct structure", () => {
    const dev = new BaseRtmDevice(makeConfig());
    const report = dev.createReport(REPORT_TIME);

    expect(report).toBeInstanceOf(RtmdReport);
    expect(report.CID).toBe("KEN");
    expect(report.AMFR).toBe("Vestfrost");
    expect(report.AMOD).toBe("VLS-054");
    expect(report.APQS).toBe("E003/034");
    expect(report.EMFR).toBe("B Medical");
    expect(report.EMOD).toBe("WT-100");
    expect(report.records).toHaveLength(4); // 3600/900
  });

  it("report records have RTMD fields", () => {
    const dev = new BaseRtmDevice(makeConfig());
    const report = dev.createReport(REPORT_TIME);
    const rec = report.records[0];

    expect(rec).toBeInstanceOf(RtmdRecord);
    expect(rec.ABST).toBeInstanceOf(Date);
    expect(typeof rec.TVC).toBe("number");
    expect(typeof rec.TAMB).toBe("number");
    expect(typeof rec.BEMD).toBe("number");
  });

  it("RTMD report has separate logger metadata from appliance", () => {
    const dev = new BaseRtmDevice(makeConfig());
    const report = dev.createReport(REPORT_TIME);
    // Logger identity comes from the RTMD device, not the appliance
    expect(report.EMFR).toBe("B Medical");
    expect(report.AMFR).toBe("Vestfrost");
    expect(report.EMFR).not.toBe(report.AMFR);
  });

  it("RTMD report carries cce-interop AMID and a coherent DLST", () => {
    const dev = new BaseRtmDevice(makeConfig());
    const json = dev.createReport(REPORT_TIME).toJSON();

    // AMID: supplier-internal id, present and a non-empty string.
    expect(typeof json.AMID).toBe("string");
    expect(json.AMID.length).toBeGreaterThan(0);

    // DLST: maps performance properties to sensor definitions; TVC required.
    expect(json.DLST).toHaveProperty("TVC");
    expect(json.DLST).toHaveProperty("TAMB");
    for (const prop of ["TVC", "TAMB"]) {
      const sensor = json.DLST[prop];
      expect(sensor).toMatchObject({
        SID: expect.any(String),
        SMFR: dev.emfr, // sensor maker mirrors the EMD/logger manufacturer
        SMOD: expect.any(String),
        SDOP: dev.edop,
      });
      expect(sensor.SID).toContain(dev.eser); // RTMD serial + sensor port
    }
    // Distinct sensor ports per property.
    expect(json.DLST.TVC.SID).not.toBe(json.DLST.TAMB.SID);
  });

  it("AMID is stable across sequential reports from the same device", () => {
    const dev = new BaseRtmDevice(makeConfig());
    const a = dev.createReport(REPORT_TIME);
    const b = dev.createReport(new Date(REPORT_TIME.getTime() + 3600 * 1000));
    expect(a.AMID).toBe(b.AMID);
  });
});

// ---------------------------------------------------------------------------
// BaseRtmDevice — EMS
// ---------------------------------------------------------------------------

describe("BaseRtmDevice (EMS)", () => {
  it("EMS logger mirrors appliance identity", () => {
    const dev = new BaseRtmDevice(makeEmsConfig());
    expect(dev.lmfr).toBe(dev.amfr);
    expect(dev.lmod).toBe(dev.amod);
    expect(dev.lpqs).toBe(dev.apqs);
    // EMD also mirrors
    expect(dev.emfr).toBe(dev.amfr);
    expect(dev.emod).toBe(dev.amod);
  });

  it("createReport returns an EmsReport", () => {
    const dev = new BaseRtmDevice(makeEmsConfig());
    const report = dev.createReport(REPORT_TIME);

    expect(report).toBeInstanceOf(EmsReport);
    expect(report.CID).toBe("NGA");
    expect(report.AMFR).toBe("Haier");
    expect(report.AMOD).toBe("HBC-200");
    expect(report.LMFR).toBe("Haier"); // mirrors appliance
    expect(report.records).toHaveLength(4);
  });

  it("EMS report metadata: ADOP, ASER, APQS present", () => {
    const dev = new BaseRtmDevice(makeEmsConfig());
    const report = dev.createReport(REPORT_TIME);
    expect(report.ADOP).toBeDefined();
    expect(report.ASER).toBeDefined();
    expect(report.APQS).toBe("E003/100");
  });

  it("EMS records have correct field types", () => {
    const dev = new BaseRtmDevice(makeEmsConfig());
    const report = dev.createReport(REPORT_TIME);
    const rec = report.records[0];

    expect(rec.ABST).toBeInstanceOf(Date);
    expect(typeof rec.TVC).toBe("number");
    expect(typeof rec.TAMB).toBe("number");
  });
});

// ---------------------------------------------------------------------------
// Sequential reports — state continuity
// ---------------------------------------------------------------------------

describe("Sequential reports", () => {
  it("state persists between createReport calls", () => {
    const dev = new BaseRtmDevice(makeConfig());
    let t = new Date(REPORT_TIME);

    const reports = [];
    for (let i = 0; i < 5; i++) {
      reports.push(dev.createReport(t));
      t = new Date(t.getTime() + 3600_000);
    }

    expect(dev.simulatorState).not.toBeNull();
    for (const r of reports) {
      expect(r.records).toHaveLength(4);
    }
  });

  it("record timestamps are correctly spaced", () => {
    const dev = new BaseRtmDevice(makeEmsConfig());
    const report = dev.createReport(REPORT_TIME);
    const timestamps = report.records.map((r) => r.ABST.getTime());

    for (let i = 1; i < timestamps.length; i++) {
      expect(timestamps[i] - timestamps[i - 1]).toBe(900_000);
    }
  });

  it("TVC stays in reasonable range over many reports", () => {
    const dev = new BaseRtmDevice(makeEmsConfig());
    let t = new Date(REPORT_TIME);
    const allTvcs = [];

    for (let i = 0; i < 10; i++) {
      const report = dev.createReport(t);
      for (const rec of report.records) {
        allTvcs.push(rec.TVC);
      }
      t = new Date(t.getTime() + 3600_000);
    }

    expect(Math.min(...allTvcs)).toBeGreaterThan(-10);
    expect(Math.max(...allTvcs)).toBeLessThan(20);
  });
});

// ---------------------------------------------------------------------------
// Reported coordinates
//
// Every report carries a fresh gauss(0.00001, 0.001) degree offset per axis,
// mirroring ccesim/facilities.py get_nudged_coordinates(). These tests pin a
// seed so nothing here is merely probable -- given the seed the values are
// fixed -- and then assert only loose, order-of-magnitude bounds on top, so a
// change of PRNG or of the draw order cannot make them flake.
// ---------------------------------------------------------------------------

const JITTER_SIGMA = 0.001; // degrees, ~111 m
const COORD_SEED = 20260729;

/** A device whose coordinate jitter is seeded, hence deterministic. */
function makeSeededDevice(overrides = {}, type = "rtmd") {
  const base = type === "ems" ? makeEmsConfig : makeConfig;
  const cfg = base(overrides);
  const simConfig = defaultConfig(cfg.powerType, cfg.lat ?? 0);
  simConfig.random_seed = COORD_SEED;
  cfg.simConfig = simConfig;
  return new BaseRtmDevice(cfg);
}

/** N sequential reports, one per hour. */
function sequentialReports(dev, n) {
  const reports = [];
  let t = new Date(REPORT_TIME);
  for (let i = 0; i < n; i++) {
    reports.push(dev.createReport(t));
    t = new Date(t.getTime() + 3600_000);
  }
  return reports;
}

describe("Reported coordinates are jittered", () => {
  it("LAT/LNG are offset from the configured coordinates", () => {
    const dev = makeSeededDevice();
    const report = dev.createReport(REPORT_TIME);

    expect(report.LAT).not.toBe(dev.config.lat);
    expect(report.LNG).not.toBe(dev.config.lng);
    // Offset is of the right order: a fraction of a degree, not a degree.
    expect(Math.abs(report.LAT - dev.config.lat)).toBeLessThan(
      12 * JITTER_SIGMA,
    );
    expect(Math.abs(report.LNG - dev.config.lng)).toBeLessThan(
      12 * JITTER_SIGMA,
    );
  });

  it("EMS reports carry the jitter too", () => {
    const dev = makeSeededDevice({}, "ems");
    const report = dev.createReport(REPORT_TIME);

    expect(report).toBeInstanceOf(EmsReport);
    expect(report.LAT).not.toBe(dev.config.lat);
    expect(report.LNG).not.toBe(dev.config.lng);
    expect(Math.abs(report.LAT - dev.config.lat)).toBeLessThan(
      12 * JITTER_SIGMA,
    );
    expect(Math.abs(report.LNG - dev.config.lng)).toBeLessThan(
      12 * JITTER_SIGMA,
    );
  });

  it("is drawn afresh for every report", () => {
    const dev = makeSeededDevice();
    const [a, b] = sequentialReports(dev, 2);

    expect(a.LAT).not.toBe(b.LAT);
    expect(a.LNG).not.toBe(b.LNG);
  });

  it("does not mutate the device's configured coordinates", () => {
    const dev = makeSeededDevice();
    sequentialReports(dev, 5);

    expect(dev.lat).toBe(-1.3);
    expect(dev.lng).toBe(36.8);
    expect(dev.config.lat).toBe(-1.3);
    expect(dev.config.lng).toBe(36.8);
  });

  it("offsets over many reports are all distinct and of the right scale", () => {
    const dev = makeSeededDevice();
    const n = 200;
    const offsets = sequentialReports(dev, n).map(
      (r) => r.LAT - dev.config.lat,
    );

    // Every report drew its own value.
    expect(new Set(offsets).size).toBe(n);
    // None of them is a degree-scale error, and none is the raw value.
    for (const d of offsets) {
      expect(Math.abs(d)).toBeLessThan(12 * JITTER_SIGMA);
      expect(d).not.toBe(0);
    }
    // Spread is of order sigma, not 0 and not 1 degree. Wide bounds: with the
    // seed pinned this is a fixed number, and 200 samples put the true value
    // well inside.
    const mean = offsets.reduce((a, b) => a + b, 0) / n;
    const sd = Math.sqrt(
      offsets.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1),
    );
    expect(sd).toBeGreaterThan(JITTER_SIGMA / 3);
    expect(sd).toBeLessThan(JITTER_SIGMA * 3);
  });

  it("is deterministic under a fixed seed", () => {
    const a = sequentialReports(makeSeededDevice(), 3).map((r) => r.LAT);
    const b = sequentialReports(makeSeededDevice(), 3).map((r) => r.LAT);
    expect(a).toEqual(b);
  });

  it("leaves unset coordinates unset rather than nudging null", () => {
    const dev = makeSeededDevice({ lat: null, lng: null });
    const report = dev.createReport(REPORT_TIME);

    expect(report.LAT).toBeNull();
    expect(report.LNG).toBeNull();
  });

  it("does not perturb the record stream", () => {
    // The coordinate RNG is a separate stream: drawing a jittered LAT/LNG must
    // not shift a single measurement. Same seed, same simulation config, only
    // the presence of coordinates differs.
    const mk = (lat, lng) => {
      const simConfig = defaultConfig("mains", -1.3);
      simConfig.random_seed = COORD_SEED;
      return new BaseRtmDevice(makeConfig({ lat, lng, simConfig }));
    };

    const a = mk(-1.3, 36.8).createReport(REPORT_TIME).records.map((r) => r.TVC);
    const b = mk(null, null).createReport(REPORT_TIME).records.map((r) => r.TVC);
    expect(a).toEqual(b);
  });
});

// ---------------------------------------------------------------------------
// transferMetadata / randomSerial
// ---------------------------------------------------------------------------

describe("transferMetadata", () => {
  it("returns correct structure for RTMD", () => {
    const meta = transferMetadata("rtmd");
    expect(meta.transferId).toBeDefined();
    expect(meta.transferSrc).toBe("org.nhgh");
    expect(meta.transferType).toBe("rtm");
    expect(meta.schemaVersion).toBe("0.8.1");
    // transferCallbackUrl is omitted entirely when no webhook URL is supplied.
    expect(meta).not.toHaveProperty("callbackUrl");
    expect(meta).not.toHaveProperty("transferCallbackUrl");
    expect(meta.transferredAt).toBeInstanceOf(Date);
  });

  it("returns ems transferType and semver schemaVersion for EMS", () => {
    const meta = transferMetadata("ems");
    expect(meta.transferType).toBe("ems");
    expect(meta.schemaVersion).toBe("0.8.1");
  });

  it("defaults to the packaged SCHEMA_VERSION constant", () => {
    // One source of truth: the class default and the function must agree.
    expect(transferMetadata("ems").schemaVersion).toBe(SCHEMA_VERSION);
    expect(new TransferMetadata({ transferId: "x" }).schemaVersion).toBe(
      SCHEMA_VERSION,
    );
  });

  it("accepts a schemaVersion override", () => {
    // Relabels the transmission; nothing else about the payload changes.
    const meta = transferMetadata("ems", null, "0.8.0");
    expect(meta.schemaVersion).toBe("0.8.0");
    expect(meta.transferType).toBe("ems");
  });

  it("falls back to the default when the override is empty", () => {
    expect(transferMetadata("ems", null, "").schemaVersion).toBe(SCHEMA_VERSION);
  });

  it("defaults to the packaged TRANSFER_SRC constant", () => {
    // One source of truth: the class default and the function must agree, and
    // with no override the wire value is unchanged from before this knob.
    expect(TRANSFER_SRC).toBe("org.nhgh");
    expect(transferMetadata("rtmd").transferSrc).toBe(TRANSFER_SRC);
    expect(transferMetadata("ems").transferSrc).toBe("org.nhgh");
    expect(new TransferMetadata({ transferId: "x" }).transferSrc).toBe(
      TRANSFER_SRC,
    );
  });

  it("accepts a transferSrc override", () => {
    // Re-attributes the transmission; nothing else about the payload changes.
    const meta = transferMetadata("ems", null, null, "com.mycompany");
    expect(meta.transferSrc).toBe("com.mycompany");
    expect(meta.transferType).toBe("ems");
    expect(meta.schemaVersion).toBe(SCHEMA_VERSION);
    // RTMD takes the same override.
    const rtm = transferMetadata("rtmd", null, null, "com.mycompany");
    expect(rtm.transferSrc).toBe("com.mycompany");
    expect(rtm.transferType).toBe("rtm");
  });

  it("falls back to the default when the transferSrc override is empty", () => {
    expect(transferMetadata("ems", null, null, "").transferSrc).toBe(
      TRANSFER_SRC,
    );
  });
});

describe("randomSerial", () => {
  it("returns a 32-char hex string", () => {
    const s = randomSerial();
    expect(s).toMatch(/^[0-9a-f]{32}$/);
  });

  it("generates unique values", () => {
    const a = randomSerial();
    const b = randomSerial();
    expect(a).not.toBe(b);
  });
});
