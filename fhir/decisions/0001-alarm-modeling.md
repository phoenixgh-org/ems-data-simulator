# ADR 0001 — Modeling ALRM/EERR/LERR: Observation base + DetectedIssue episodes

- **Status:** Accepted (subject to confirmation with a country / eLMIS consumer)
- **Decision bead:** `ccesim-jby.3`
- **Date:** 2026-06-16
- **Affects:** Phase 2 transform (`fhir/transform/`), Phase 3 profiles (`ccesim-jby.5`)

## Context

The EMS data objects `ALRM`, `EERR`, and `LERR` carry coded state, not numeric
measurements. `ALRM` is a space-delimited string of WHO PQS E003 alarm codes
(`HEAT`/`FRZE`/`DOOR`/`POWR`); `EERR`/`LERR` are EMD/logger fault codes.

The defining characteristic: **EMS alarms are excursion-timer episodes.** An alarm
(e.g. `HEAT` = TVC > 8 °C for 10 continuous hours) stays active across many
consecutive records once it fires. In the example dataset, a single HEAT
excursion spans **65 consecutive records** — which as one-Observation-per-record
produces 65 near-identical resources.

Three candidate FHIR representations were considered:

| Resource | Fit |
|----------|-----|
| **Observation** (coded value) | Lossless, 1:1 with the wire; uniform to query alongside temperatures; answers "what did the device report at time T". But noisy — a multi-day excursion becomes hundreds of identical resources. |
| **DetectedIssue** | "An identified problem/risk." `identifiedPeriod` + `code` + `severity` + `implicated` naturally model one alarm *episode*; collapses the 65 records to 1. Alert/dedup-friendly. |
| **Flag** | Rejected — `Flag` is a *prospective* warning surfaced to a clinician during care, not a record of a *detected* event. Wrong intent. |

## Decision

**Dual representation, by purpose:**

1. **Per-record codes → coded `Observation` (the lossless base).** Keep what the
   Phase 2 transform already does: every `ALRM`/`EERR`/`LERR` code on a record
   becomes a coded `Observation` (`valueCodeableConcept`). This is the faithful,
   reversible projection of the wire data and queries uniformly with telemetry.

2. **E003 alarm *conditions* → also derive one `DetectedIssue` per episode.** For
   the vaccine-safety alarms (`HEAT`/`FRZE`/`DOOR`/`POWR`), the interoperability
   layer derives a `DetectedIssue` per contiguous episode: `identifiedPeriod`
   covering the excursion, `code` from `PqsE003Alarms`, `severity`
   (HEAT/FRZE → high, DOOR/POWR → moderate), and `implicated` referencing the
   appliance `Device`. Prototype: `fhir/transform/alarm_episodes.py` — validates
   against **FHIR R4 (4.0.1)** with 0 errors; the example HEAT excursion yields
   **1 DetectedIssue vs 65 Observations**.

3. **`EERR`/`LERR` (device faults) → `Observation` only, for now.** These are
   device-health signals, not vaccine-safety events; they do not warrant
   `DetectedIssue` by default. A fault that is genuinely actionable can be
   promoted to `DetectedIssue` later without changing the base representation.

`DetectedIssue` is *derived*, not transmitted: suppliers still send raw per-record
`ALRM`/`EERR`/`LERR` per the EMS spec; the episode rollup is a country-side
interop-layer transform (consistent with the overview's "interoperability layer
derives indicators" model).

## Consequences

- Phase 3 (`ccesim-jby.5`) profiles `DetectedIssue` and adds `evidence.detail`
  links from each episode to its contributing temperature `Observation`s, and
  decides the severity taxonomy with a consumer in the loop.
- The base `Observation` stream is unchanged, so nothing about this decision
  blocks or rewrites Phase 2.
- Open for confirmation: whether downstream consumers (eLMIS/HMIS) prefer episodes
  keyed differently (e.g. per-day rollups) — the interop layer can offer multiple
  derivations off the same `Observation` base.
