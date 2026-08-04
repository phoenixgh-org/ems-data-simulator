# ADR 0002 — Pinning the transform PoC's acceptance counts in the script, not in `tests/`

- **Status:** Accepted
- **Date:** 2026-08-03
- **Affects:** `fhir/transform/run_phase2_poc.py`, the `fhir-transform` CI job
- **Closes:** ccesim-58y

## Context

`fhir/transform/run_phase2_poc.py` is a CI gate (ccesim-33o). ccesim-fhl.2 seeded
it — `random.seed(101)` plus `sim_config.random_seed` — so its printed acceptance
counts became reproducible. But nothing *enforced* that reproducibility:

- The CI job runs the script and checks only its exit code.
- The alarm check asserted `len(alarms) > 0`, not a specific count.

So a future change that reintroduced an unseeded draw — a new random source in
`ccesim/device.py`, a default that stopped honouring `sim_config.random_seed` —
would keep the gate green while silently generating different data. That is the
latent-flake condition ccesim-fhl.2 was filed to remove, left half-closed.

ccesim-58y proposed asserting the pinned tuple (3 Devices / 8903 Observations /
8640 quantity / 260 coded alarms) somewhere automated, and named the real
constraint: **the run takes ~1 minute.** The unit suite is 340 tests in ~2.8 s.
Putting a one-minute scenario in `tests/` would inflate it by ~20×, which is the
kind of cost that gets a test deleted or marked skip a year later.

Two candidates:

| Option | Fit |
|--------|-----|
| **Pin the counts inside the script's `assert_acceptance()`** | The dedicated CI job already runs this script and already fails on non-zero exit. Costs no additional wall-clock anywhere — the run was happening regardless. |
| **A separate CI step running the script twice and diffing stdout** | Catches the same class of regression without naming expected numbers, so it needs no updating on intended changes. But it pays a *second* ~1 minute run and needs new workflow logic. It also only detects run-to-run variance, not a deterministic change to the wrong values. |

## Decision

**Pin the four counts inside `assert_acceptance()` in `run_phase2_poc.py`.**

These assertions are **not** part of the pytest suite. They live in a standalone
driver executed by its own CI job ("FHIR transform acceptance checks"), invoked as
`pipenv run python fhir/transform/run_phase2_poc.py`. `tests/` neither imports nor
runs this file. That separation is the whole point: the unit suite stays at ~2.8 s
and pays nothing, while the pinned counts still gate every push.

`main()` ANDs all checks and returns 1 on any failure, so a broken pin fails the
job.

## Consequences

- **`SEED` is fixed, not a dial.** On failure the fork is: intended change → re-pin
  the four numbers in the same commit; unexplained shift → an unpinned draw crept
  back in, fix the draw. Re-seeding to make the gate pass would launder exactly the
  regression this ADR exists to catch. The code comment says so at the assertion site.
- **Intended transform changes now cost a re-pin.** Accepted deliberately — that
  edit is the signal that output changed, and it lands in the diff for review.
- **`len(devs) == 3` is structural, not a determinism guard.** One appliance + EMD +
  logger on every run; it passes under any seed. Kept as shape documentation. The
  other three checks carry the guard — all three were verified to fail under a
  perturbed seed (seed 4242 → 8004 / 7776 / 228).
- **This pins the counts, not the emitted artefacts.** Per ccesim-67j (open), the
  device serials, AMID, `transferId` and `transferredAt` come from `uuid4()` and
  `datetime.now()` and ignore `random.seed()`, so `fhir/examples/*.json` is not
  byte-reproducible. Those values never reach stdout and do not affect any count,
  so the gate is sound — but "seeded" should not be read as "the example files are
  reproducible." (`fhir/examples/` is gitignored, so git will not show that drift.)
