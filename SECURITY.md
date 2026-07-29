# Security Policy

## What this project is, and what that means for risk

This is a **synthetic data generator**. It produces cold chain equipment
monitoring data from a thermal model, entirely from first principles. It has:

- no authentication or authorisation of its own,
- no network listener, no server, no web interface,
- no database,
- and **no real patient, personal or facility-identifying data** — the packaged
  catalogs are illustrative samples and published WHO PQS equipment references,
  and the temperature series are computed, not replayed from a real fleet.

So the usual application-security surface is largely absent. The realistic
concerns are narrower, and they are the ones worth reporting:

- **Vulnerable dependencies.** The Python side depends on Pydantic and a few
  date/time libraries; the JavaScript side on `seedrandom`, with `vitest` for
  tests. A vulnerability in any of these is in scope.
- **The third-party reference data shipped in the repo.** Facility, appliance and
  logger catalogs, and the FHIR terminology under `fhir/`. Report it if any of it
  turns out to contain something it should not — real identifiable facility or
  device data, or content whose licence does not permit redistribution.
- **Anything that would let generated input reach a consumer as trusted data.**
  The simulator's output is fed to validators and ingestion pipelines; a crafted
  config that produces a payload able to subvert a downstream consumer (rather
  than simply fail validation) is worth telling us about.
- **Code execution from untrusted input.** Catalog files are parsed as JSON and
  CSV. If a catalog file can do more than supply data, that is a bug we want.

The one place credentials exist is the optional Locust load-testing harness
(`locustfile.py`), which posts to a delivery endpoint you configure. Those
credentials live in `.env`, which is gitignored. Keep them there; do not commit
them, and do not point the load tester at a production endpoint you do not own.

## Supported versions

There has been no tagged release. Fixes land on `main`, and `main` is what is
supported. If you are using a pinned commit, expect to move forward to pick up a
fix.

## Reporting a vulnerability

Please report privately, not as a public GitHub issue:

- **Preferred:** open a private security advisory —
  <https://github.com/phoenixgh-org/ems-data-simulator/security/advisories/new>
- **Or by email:** benson.miller@gmail.com

Useful things to include: what you found, how to reproduce it, and what you think
the impact is on someone using the simulator or consuming its output.

This project is maintained by a small team without a dedicated security rota, so
**we will not promise a response time we cannot keep**. We will acknowledge your
report and tell you what we intend to do about it, and we will credit you when a
fix lands unless you would rather we did not. If a report has real impact on
downstream cold chain systems, say so plainly — that is what gets it looked at
first.

Please give us a reasonable chance to fix an issue before disclosing it publicly.
