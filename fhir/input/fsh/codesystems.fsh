// =============================================================================
// CodeSystems for WHO PQS E006 EMS / CCE data
//
// Source of truth:
//   - WHO/PQS/E006/DS01 Annex 1 (Cold Chain Data Objects) + Annex 2 (JSON Schema)
//   - cce-interop-0.8.1 $defs/PQS-DS01-objects (derived delivery schema)
// Concept displays/definitions are lifted verbatim from the schema titles &
// descriptions. There is no off-the-shelf code system for these; the PQS code
// is the PRIMARY code, with ConceptMaps to LOINC/UCUM authored later.
//
// GOVERNANCE (open question): the canonical URLs below use a
// placeholder host. Ownership of the canonical namespace (WHO/PQS vs the
// interop-requirements maintainers) is unresolved and must be settled before
// publication.
// =============================================================================

CodeSystem: PqsE006DataObjects
Id: pqs-e006-data-objects
Title: "WHO PQS E006 EMS Data Object Codes"
Description: "Four-letter EMS/CCE data object identifiers from WHO/PQS/E006/DS01 Annex 1, as expressed in the cce-interop delivery schema. Each concept is one monitored or administrative data object."
* ^url = "https://worldhealthorg.example/fhir/cce/CodeSystem/pqs-e006-data-objects"
* ^status = #draft
* ^experimental = true
* ^caseSensitive = true
* ^content = #complete
* #ABST "Absolute time in UTC"
  * ^definition = "Absolute time measured in UTC"
* #ACAT "Appliance PQS device type"
  * ^definition = "PQS device type or category"
* #ACCD "AC current drawn by the appliance"
  * ^definition = "Average AC current being drawn from supply by the operation of the appliance within each 15 minute period. Average value of raw samples collected at intervals not longer than 10 seconds."
* #ACSV "AC supply voltage to the appliance"
  * ^definition = "Average AC supply voltage to appliance within each 15 minute period. Average value of raw samples collected at intervals not longer than 10 seconds."
* #ADOP "Appliance date of production"
  * ^definition = "Date of manufacture"
* #AID "Appliance identifier"
  * ^definition = "Identifier for program asset tracking."
* #ALRM "Alarm condition"
  * ^definition = "Presence of defined alarm conditions"
* #AMFR "Appliance manufacturer"
  * ^definition = "Manufacturer name"
* #AMOD "Appliance model"
  * ^definition = "Manufacturer model number"
* #APQS "Appliance PQS code"
  * ^definition = "PQS code (E00X/XXX)"
* #ASER "Appliance manufacturer serial number"
  * ^definition = "Manufacturer serial number"
* #BEMD "EMD battery remaining"
  * ^definition = "Estimated number of days of battery life remaining"
* #BLOG "Logger battery remaining"
  * ^definition = "Estimated number of days of battery life remaining"
* #CDAT "Compressor Electronic Unit production date"
  * ^definition = "Compressor electronic unit admin information"
* #CDAT2 "Secondary Compressor Electronic Unit production date"
  * ^definition = "Compressor electronic unit admin information"
* #CID "Country ID"
  * ^definition = "Country where monitored appliance is located"
* #CMPR "Compressor runtime"
  * ^definition = "Total duration compressor operated within each 15 minute period measured in seconds"
* #CMPR2 "Secondary Compressor runtime"
  * ^definition = "Total duration compressor operated within each 15 minute period measured in seconds"
* #CMPS "Compressor speed"
  * ^definition = "Maximum operating speed of the compressor in revolutions per minute within each 15-minute period, based on samples collected at intervals not longer than 10 seconds"
* #CMPS2 "Secondary compressor speed"
  * ^definition = "Maximum operating speed of the compressor in revolutions per minute within each 15-minute period, based on samples collected at intervals not longer than 10 seconds"
* #CNAM "Compressor Electronic Unit Manufacturer"
  * ^definition = "Compressor electronic unit admin information"
* #CNAM2 "Secondary Compressor Electronic Unit Manufacturer"
  * ^definition = "Compressor electronic unit admin information"
* #CSER "Compressor Electronic Unit Product Code"
  * ^definition = "Compressor electronic unit admin information"
* #CSER2 "Secondary Compressor Electronic Unit Product Code"
  * ^definition = "Compressor electronic unit admin information"
* #CSOF "Compressor Electronic Unit Software version"
  * ^definition = "Compressor electronic unit admin information"
* #CSOF2 "Secondary Compressor Electronic Unit Software version"
  * ^definition = "Compressor electronic unit admin information"
* #DCCD "DC current drawn by the appliance"
  * ^definition = "Average DC current being drawn from supply by the operation of the appliance within each 15 minute period. Average value of raw samples collected at intervals not longer than 10 seconds."
* #DCSV "DC supply voltage to the appliance"
  * ^definition = "Average DC supply voltage to appliance within each 15 minute period. Average value of raw samples collected at intervals not longer than 10 seconds."
* #DNAM "District Name"
  * ^definition = "Name of district where device is located"
* #DORF "Door/lid opening (freezer/other compartment)"
  * ^definition = "Total duration freezer compartment or other compartment door was opened within each 15 minute period measured in seconds"
* #DORV "Door/lid opening (vaccine compartment)"
  * ^definition = "Total duration vaccine compartment door was opened within each 15 minute period measured in seconds"
* #DRCF "Number of door/lid openings (freezer/other compartment)"
  * ^definition = "Number of door openings within each 15-minute sample period"
* #DRCV "Number of door/lid openings (vaccine compartment)"
  * ^definition = "Number of door openings within each 15-minute sample period"
* #EDOP "EMD date of production"
  * ^definition = "Date of manufacture"
* #EERR "EMD Error Codes"
  * ^definition = "Alphanumeric codes corresponding to conditions that may impair normal operation of the EMD (e.g. broken or disconnected sensors, self-test failure)"
* #EID "EMD identifier"
  * ^definition = "Identifier for program asset tracking"
* #EMFR "EMD manufacturer"
  * ^definition = "Manufacturer name"
* #EMOD "EMD model"
  * ^definition = "Manufacturer model number"
* #EMSV "EMD software version"
  * ^definition = "Version number of EMD software/firmware installed"
* #EPQS "EMD PQS code"
  * ^definition = "PQS code (E00X/XXX)"
* #ESER "EMD serial number"
  * ^definition = "Manufacturer serial number"
* #FANS "Fan speed"
  * ^definition = "Min. 0% / Max. 100% speed"
* #FID "Facility ID"
  * ^definition = "Facility where monitored appliance is located"
* #FNAM "Facility Name"
  * ^definition = "Name of facility where device is located"
* #HAMB "Ambient relative humidity"
  * ^definition = "RH%"
* #HCOM "Compartment relative humidity"
  * ^definition = "RH%"
* #HOLD "Holdover autonomy or independence time"
  * ^definition = "estimated time in days during which all points in the vaccine compartment remain between +2C and +8C if supply power disconnected"
* #IDRF "Instantaneous door/lid opening (freezer compartment)"
  * ^definition = "Total continuous duration freezer compartment door has been open at time of USB mount"
* #IDRV "Instantaneous door/lid opening (vaccine compartment)"
  * ^definition = "Total continuous duration vaccine compartment door has been open at time of USB mount"
* #LACC "Location accuracy (in meters)"
  * ^definition = "Accuracy of location information, in meters"
* #LAT "Location / GIS Coordinates / Latitude"
  * ^definition = "Physical location of asset"
* #LDOP "Logger date of production"
  * ^definition = "Date of manufacture"
* #LERR "Logger Error Codes"
  * ^definition = "Alphanumeric codes corresponding to conditions that may impair normal operation of the Logger (e.g. broken or disconnected sensors, self-test failure)"
* #LID "Logger identifier"
  * ^definition = "Identifier for program asset tracking"
* #LMFR "Logger manufacturer"
  * ^definition = "Manufacturer name"
* #LMOD "Logger model"
  * ^definition = "Manufacturer model number"
* #LNG "Location / GIS Coordinates / Longitude"
  * ^definition = "Physical location of asset"
* #LPQS "Logger PQS code"
  * ^definition = "PQS code (E00X/XXX)"
* #LSER "Logger serial number"
  * ^definition = "Manufacturer serial number"
* #LSV "Logger software version"
  * ^definition = "Version number of Logger software/firmware installed"
* #MSW "Main ON/OFF switch"
  * ^definition = "OFF (false) / ON (true) of main control switch of appliance"
* #RNAM "Region Name"
  * ^definition = "Name of region where device is located"
* #SIGN "File Integrity check"
  * ^definition = "Integrity check on file contents; could be CRC hash or signature"
* #SVA "AC Supply voltage availability"
  * ^definition = "Data indicating the number of seconds within each 15-minute period when the AC voltage is within acceptable bounds to operate the appliance"
* #TAMB "Ambient temperature"
  * ^definition = "Temperature of the immediate appliance surroundings; should not be affected by appliance operation"
* #TCON "Condenser temperature"
  * ^definition = "Temperature of the condenser"
* #TCON2 "Secondary Condenser temperature"
  * ^definition = "Temperature of the condenser"
* #TFRZ "Freezer Compartment temperature"
  * ^definition = "Temperature sensor located in a freezer compartment"
* #TPCB "Compressor Electronic Unit temperature"
  * ^definition = "Temperature of Compressor Electronic Unit"
* #TPCB2 "Secondary Compressor Electronic Unit temperature"
  * ^definition = "Temperature of Compressor Electronic Unit"
* #TVC "Vaccine Compartment temperature"
  * ^definition = "Temperature sensor located in coldest location of storage compartment"

CodeSystem: PqsE003Alarms
Id: pqs-e003-alarms
Title: "WHO PQS E003 Alarm Condition Codes"
Description: "Alarm condition codes reported in the EMS ALRM data object. The wire format of ALRM is a space-delimited string that may carry more than one of these codes simultaneously (e.g. \"HEAT DOOR\"). Thresholds shown are the WHO PQS E003 reference conditions."
* ^url = "https://worldhealthorg.example/fhir/cce/CodeSystem/pqs-e003-alarms"
* ^status = #draft
* ^experimental = true
* ^caseSensitive = true
* ^content = #complete
* #HEAT "High-temperature excursion"
  * ^definition = "Vaccine compartment temperature (TVC) above the high threshold (e.g. > +8 C) for a continuous reference duration (e.g. 10 hours)."
* #FRZE "Freeze excursion"
  * ^definition = "Vaccine compartment temperature (TVC) at or below the freeze threshold (e.g. <= -0.5 C) for a continuous reference duration (e.g. 60 minutes)."
* #DOOR "Door/lid open too long"
  * ^definition = "A vaccine-compartment door/lid open continuously beyond the reference duration (e.g. 5 minutes)."
* #POWR "Power loss"
  * ^definition = "Continuous no-power (no usable supply) condition beyond the reference duration (e.g. 24 hours)."


// EMD and Logger error codes (EERR / LERR). These are partly vendor-specific;
// the E006 spec requires suppliers to provide definitions for custom codes
// (Clause 5). The concepts below are the set EMITTED BY THIS SIMULATOR and are
// illustrative, NOT an authoritative master list. Real deployments will extend
// or replace these per supplier-supplied definitions.

CodeSystem: CceEmdErrorCodes
Id: cce-emd-error-codes
Title: "CCE EMD Error Codes (illustrative)"
Description: "EMD error codes (EERR data object). Illustrative set emitted by the CCE simulator; suppliers provide authoritative definitions per WHO/PQS/E006 Clause 5."
* ^url = "https://worldhealthorg.example/fhir/cce/CodeSystem/cce-emd-error-codes"
* ^status = #draft
* ^experimental = true
* ^caseSensitive = true
* ^content = #fragment
* #1 "EMD error 1"
* #2 "EMD error 2"
* #3 "EMD error 3"
* #4 "EMD error 4"
* #5 "EMD error 5"
* #6 "EMD error 6"
* #7 "EMD error 7"
* #COMM "Communication fault"

CodeSystem: CceLoggerErrorCodes
Id: cce-logger-error-codes
Title: "CCE Logger Error Codes (illustrative)"
Description: "Logger error codes (LERR data object). Illustrative set emitted by the CCE simulator; suppliers provide authoritative definitions per WHO/PQS/E006 Clause 5."
* ^url = "https://worldhealthorg.example/fhir/cce/CodeSystem/cce-logger-error-codes"
* ^status = #draft
* ^experimental = true
* ^caseSensitive = true
* ^content = #fragment
* #COMM "Communication fault"
* #SENS "Sensor fault"
* #BATT "Battery fault"
* #RTC "Real-time clock fault"
* #MEM "Memory/storage fault"
