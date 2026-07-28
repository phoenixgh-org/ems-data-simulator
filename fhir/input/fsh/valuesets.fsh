// =============================================================================
// ValueSets for WHO PQS E006 EMS / CCE data
//
// These value sets are referenced by the Logical Model field bindings
// (logical-models.fsh) and will be reused by the Observation profiles in
// a future profiling pass.
// =============================================================================

ValueSet: PqsE006DataObjectsVS
Id: pqs-e006-data-objects-vs
Title: "WHO PQS E006 EMS Data Object Codes"
Description: "All EMS/CCE data object codes. Used to identify which data object an Observation represents."
* ^url = "https://worldhealthorg.example/fhir/cce/ValueSet/pqs-e006-data-objects-vs"
* ^status = #draft
* ^experimental = true
* include codes from system PqsE006DataObjects

ValueSet: PqsE003AlarmsVS
Id: pqs-e003-alarms-vs
Title: "WHO PQS E003 Alarm Condition Codes"
Description: "Alarm condition codes that may appear in the ALRM data object."
* ^url = "https://worldhealthorg.example/fhir/cce/ValueSet/pqs-e003-alarms-vs"
* ^status = #draft
* ^experimental = true
* include codes from system PqsE003Alarms

ValueSet: CceEmdErrorCodesVS
Id: cce-emd-error-codes-vs
Title: "CCE EMD Error Codes (illustrative)"
Description: "EMD error codes (EERR). Extensible: suppliers add custom codes per E006 Clause 5."
* ^url = "https://worldhealthorg.example/fhir/cce/ValueSet/cce-emd-error-codes-vs"
* ^status = #draft
* ^experimental = true
* include codes from system CceEmdErrorCodes

ValueSet: CceLoggerErrorCodesVS
Id: cce-logger-error-codes-vs
Title: "CCE Logger Error Codes (illustrative)"
Description: "Logger error codes (LERR). Extensible: suppliers add custom codes per E006 Clause 5."
* ^url = "https://worldhealthorg.example/fhir/cce/ValueSet/cce-logger-error-codes-vs"
* ^status = #draft
* ^experimental = true
* include codes from system CceLoggerErrorCodes
