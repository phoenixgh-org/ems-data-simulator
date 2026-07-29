/**
 * Public API for the EMS data simulator.
 */

// Recordset & state
export { SimulatedRecordSet, SimulatorState } from "./recordset.js";

// Configuration
export {
  SimulationConfig,
  ThermalConfig,
  AmbientConfig,
  PowerConfig,
  EventConfig,
  FaultConfig,
  FaultType,
  defaultConfig,
} from "./config.js";

// Schemas
export {
  TransferMetadata,
  EmsRecord,
  EmsRecordMains,
  EmsRecordSolar,
  EmsReport,
  EmsTransfer,
  RtmdRecord,
  RtmdReport,
  RtmdTransfer,
  formatEmsDateTime,
} from "./schemas.js";

// Device
export {
  MonitoringDeviceConfig,
  BaseRtmDevice,
  randomSerial,
  transferMetadata,
} from "./device.js";

// Events
export { FaultEffects, DoorEvent } from "./events.js";

// Random
export { SeededRandom } from "./random.js";

// Catalogs (browser-safe core; file loading lives in ./catalogs-node.js,
// which is reached through the "ems-data-simulator/catalogs-node" subpath so
// that bundling this entry point never drags in a Node filesystem module)
export {
  Catalogs,
  CATALOG_KINDS,
  MANIFEST_FILENAME,
  MANIFEST_FIELDS,
  FACILITY_ALIASES,
  APPLIANCE_ALIASES,
  LOGGER_ALIASES,
  REQUIRED_FIELDS,
  normalizeCatalogKey,
  validateManifest,
} from "./catalogs.js";
