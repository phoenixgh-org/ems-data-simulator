// =============================================================================
// FHIR Logical Models for the WHO PQS E006 EMS / CCE data structure
//
// These StructureDefinitions (kind = logical) express the EMS data structure in
// FHIR's own modeling language, mirroring the cce-interop-0.8.1 nesting:
//
//     CceTransmission  (root: meta + data[])
//        -> CceEmsReport   (one report per CCE; administrative / static)
//             -> CceEmsRecord  (one sampling interval; volatile telemetry)
//
// Cardinalities follow the schema's `required` lists ($defs ems-report /
// ems-record). Units in [brackets] are UCUM, taken from the authoritative
// Annex-1 / schema definitions (NOTE the corrected units: HOLD and BEMD/BLOG
// are in DAYS, SVA in seconds, CMPS in rpm).
//
// FAITHFULNESS NOTE: the cce-interop wire schema is FLAT (e.g. AMFR sits at the
// report root, not under an `appliance` group) and uses ISO-BASIC timestamps
// (YYYYMMDDThhmmssZ) plus JSON nulls. This logical model GROUPS related admin
// objects into BackboneElements for clarity and types times as `instant`/`date`.
// Reconciling the logical shape with the flat wire shape is the job of the
// StructureMap, not this model.
// =============================================================================

// -----------------------------------------------------------------------------
// Root: a single supplier -> country transmission
// -----------------------------------------------------------------------------
Logical: CceTransmission
Id: cce-transmission
Title: "CCE Data Transmission"
Description: "A single supplier-to-country CCE data transmission (cce-interop schema root: a `meta` envelope plus a `data` array of reports)."
* ^url = "https://worldhealthorg.example/fhir/cce/StructureDefinition/cce-transmission"
* ^status = #draft
* ^experimental = true
* meta 1..1 BackboneElement "Transmission metadata (about the transmission, not the CCE)"
  * schemaVersion 1..1 string "Schema version the transmission validates against, e.g. 0.8.1"
  * transferType 1..1 code "Type of transmission: ems | rtmd"
  * transferId 1..1 string "Supplier-generated unique transmission ID (e.g. UUID)"
  * transferSrc 1..1 string "URI of the data transmission source"
  * transferredAt 1..1 instant "Datetime the transmission was sent (UTC)"
  * transferCallbackUrl 0..1 url "Optional webhook called with data-processing status"
* data 1..* CceEmsReport "One report per CCE (array allows batching multiple CCE or multiple reports)"

// -----------------------------------------------------------------------------
// Report: administrative / slowly-changing properties for one CCE
// -----------------------------------------------------------------------------
Logical: CceEmsReport
Id: cce-ems-report
Title: "CCE EMS Report"
Description: "Administrative and slowly-changing properties for a single CCE, plus its array of time-varying records. Mirrors the cce-interop `ems-report` subschema."
* ^url = "https://worldhealthorg.example/fhir/cce/StructureDefinition/cce-ems-report"
* ^status = #draft
* ^experimental = true
* CID 1..1 string "Country ID (country where the appliance is located)"
* appliance 1..1 BackboneElement "The refrigerator/freezer appliance being monitored"
  * AID 0..1 string "Appliance identifier (program asset tracking)"
  * AMFR 1..1 string "Appliance manufacturer"
  * AMOD 1..1 string "Appliance model number"
  * ASER 1..1 string "Appliance manufacturer serial number"
  * ADOP 1..1 date "Appliance date of production"
  * APQS 1..1 string "Appliance PQS code (E00X/XXX)"
  * ACAT 0..1 string "Appliance PQS device type/category"
* emd 1..1 BackboneElement "Electronic Monitoring Device (EMD)"
  * EID 0..1 string "EMD identifier"
  * EMFR 1..1 string "EMD manufacturer"
  * EMOD 1..1 string "EMD model number"
  * ESER 1..1 string "EMD serial number"
  * EDOP 1..1 date "EMD date of production"
  * EPQS 1..1 string "EMD PQS code"
  * EMSV 0..1 string "EMD software/firmware version"
* logger 1..1 BackboneElement "Data logger"
  * LID 0..1 string "Logger identifier"
  * LMFR 1..1 string "Logger manufacturer"
  * LMOD 1..1 string "Logger model number"
  * LSER 1..1 string "Logger serial number"
  * LDOP 1..1 date "Logger date of production"
  * LPQS 1..1 string "Logger PQS code"
  * LSV 0..1 string "Logger software/firmware version"
* compressorUnit 0..1 BackboneElement "Compressor electronic unit administrative info (primary)"
  * CNAM 0..1 string "Compressor electronic unit manufacturer"
  * CSER 0..1 string "Compressor electronic unit product code"
  * CSOF 0..1 string "Compressor electronic unit software version"
  * CDAT 0..1 date "Compressor electronic unit production date"
* compressorUnit2 0..1 BackboneElement "Compressor electronic unit administrative info (secondary)"
  * CNAM2 0..1 string "Secondary compressor electronic unit manufacturer"
  * CSER2 0..1 string "Secondary compressor electronic unit product code"
  * CSOF2 0..1 string "Secondary compressor electronic unit software version"
  * CDAT2 0..1 date "Secondary compressor electronic unit production date"
* location 0..1 BackboneElement "Facility and GIS location"
  * FID 0..1 string "Facility ID"
  * FNAM 0..1 string "Facility name"
  * DNAM 0..1 string "District name"
  * RNAM 0..1 string "Region name"
  * LAT 0..1 decimal "Latitude [-90..90]"
  * LNG 0..1 decimal "Longitude [-180..180]"
  * LACC 0..1 decimal "Location accuracy [m]"
* SIGN 0..1 string "File integrity check (CRC/hash/signature)"
* records 1..* CceEmsRecord "Time-varying performance records, one per sampling interval"

// -----------------------------------------------------------------------------
// Record: volatile telemetry for one sampling interval (typically 15 min)
// -----------------------------------------------------------------------------
Logical: CceEmsRecord
Id: cce-ems-record
Title: "CCE EMS Record"
Description: "One sampling interval of CCE telemetry (typically 15 minutes). Mirrors the cce-interop `ems-record` subschema. Required objects per schema: ABST, ALRM, BEMD, BLOG, CMPR, DORV, EERR, LERR, TAMB."
* ^url = "https://worldhealthorg.example/fhir/cce/StructureDefinition/cce-ems-record"
* ^status = #draft
* ^experimental = true
// --- time ---
* ABST 1..1 instant "Absolute timestamp of the record (UTC)"
// --- temperatures [Cel] ---
* TVC 0..1 decimal "Vaccine compartment temperature [Cel], range -55..60"
* TFRZ 0..1 decimal "Freezer compartment temperature [Cel], range -99.9..60"
* TAMB 1..1 decimal "Ambient temperature [Cel], range -55..60"
* TCON 0..1 decimal "Condenser temperature [Cel], range -55..150"
* TCON2 0..1 decimal "Secondary condenser temperature [Cel]"
* TPCB 0..1 decimal "Compressor electronic unit temperature [Cel]"
* TPCB2 0..1 decimal "Secondary compressor electronic unit temperature [Cel]"
// --- humidity [%] ---
* HAMB 0..1 decimal "Ambient relative humidity [%], range 0..100"
* HCOM 0..1 decimal "Compartment relative humidity [%], range 0..100"
// --- power: AC / DC [A], [V], availability [s] ---
* ACCD 0..1 decimal "AC current drawn by the appliance [A], range 0..50 (mean over interval)"
* ACSV 0..1 decimal "AC supply voltage [V], range 0..600 (mean over interval)"
* DCCD 0..1 decimal "DC current drawn by the appliance [A], range 0..99.9 (mean over interval)"
* DCSV 0..1 decimal "DC supply voltage [V], range 0..999.9 (mean over interval)"
* SVA 0..1 decimal "Seconds within the interval that AC voltage was in acceptable bounds [s], 0..900"
* MSW 0..1 boolean "Main ON/OFF switch state (true = ON)"
// --- compressor ---
* CMPR 1..1 decimal "Compressor runtime within the interval [s], range 0..900"
* CMPR2 0..1 decimal "Secondary compressor runtime [s], range 0..900"
* CMPS 0..1 decimal "Max compressor speed in the interval [/min] (rpm), range 0..20000"
* CMPS2 0..1 decimal "Max secondary compressor speed [/min] (rpm)"
* FANS 0..1 decimal "Fan speed [%], range 0..100"
// --- doors / lids ---
* DORV 1..1 decimal "Vaccine compartment door-open duration in the interval [s], range 0..900"
* DORF 0..1 decimal "Freezer/other compartment door-open duration [s], range 0..900"
* DRCV 0..1 decimal "Number of vaccine-compartment door openings in the interval"
* DRCF 0..1 decimal "Number of freezer/other-compartment door openings in the interval"
* IDRV 0..1 decimal "Instantaneous vaccine-compartment door-open duration at USB mount [s]"
* IDRF 0..1 decimal "Instantaneous freezer-compartment door-open duration at USB mount [s]"
// --- autonomy / batteries (DAYS) ---
* HOLD 0..1 decimal "Holdover autonomy / independence time [d] (days TVC stays in +2..+8 C if power lost), 0..999.9"
* BEMD 1..1 decimal "Estimated EMD battery life remaining [d]"
* BLOG 1..1 decimal "Estimated logger battery life remaining [d]"
// --- alarms & errors (coded) ---
// Wire format: ALRM is a space-delimited string that may carry several codes at
// once; absence/JSON-null = no alarm. Modeled here as 0..* coded for clarity;
// the StructureMap splits the wire string. (See decisions/0001-alarm-modeling.md for
// whether downstream alarms become Observation vs DetectedIssue.)
* ALRM 0..* code "Active alarm condition code(s)"
* ALRM from PqsE003AlarmsVS (required)
* EERR 0..* code "EMD error code(s)"
* EERR from CceEmdErrorCodesVS (extensible)
* LERR 0..* code "Logger error code(s)"
* LERR from CceLoggerErrorCodesVS (extensible)
