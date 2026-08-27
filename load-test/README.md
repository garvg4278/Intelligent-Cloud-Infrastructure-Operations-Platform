# load-test/

A [k6](https://k6.io/) script exercising realistic, authenticated traffic
against the gateway -- real registration + login (not a bypass), then a
read-heavy mix across deployments/incidents/analytics/audit, with think
time between requests.

## Status: written, never run

No running deployment was reachable from the sandbox this was built in --
same category of caveat as `terraform/`, `ansible/`, and `gitops/` (see
each of their READMEs). This script has been read through carefully
against k6's actual API and syntax-checked with `node --check` (k6 itself
wasn't available to run it against, but the JavaScript is at least
parseable) -- that is not the same thing as having run it, and there is
no load-test result anywhere in this repo. Every threshold in
`k6/baseline.js` is a deliberately generous starting guess, not a number
measured against anything real. **Do not repeat a number from this
script as if it were a measured fact about this platform's performance --
there isn't one yet.**

## Running it for real

```bash
# Install k6: https://k6.io/docs/get-started/installation/
k6 run -e BASE_URL=https://your-real-gateway-url load-test/k6/baseline.js
```

Points at a real, running gateway (local `docker compose up`, or a real
environment once `terraform`/`ansible`/`gitops` have actually provisioned
one). Deliberately read-only against user-data-mutating routes -- it
registers its own load-test users but never triggers a deployment or
provisions/destroys infrastructure, so it's safe to point at a real
staging environment without side effects on the platform's actual state
beyond the users it creates and the load itself.

## What this does NOT cover

- **No capacity/breaking-point test.** `k6/baseline.js` ramps to 20
  concurrent users and holds -- a smoke-level profile meant to catch
  obvious regressions, not to answer "what's the ceiling." A real
  capacity test needs its own scenario (a much higher `target`, run
  against a real environment, watched against real Grafana dashboards
  while it runs) -- not built here.
- **No write-heavy scenario.** Real traffic includes deployments being
  triggered, alerts firing, incidents being created -- this script
  doesn't exercise any of that, on purpose (see "Running it for real"
  above). A write-heavy scenario is real, valuable follow-up work.
- **No chaos/failure-injection testing.** Killing a pod mid-load, a node
  going away, RDS failing over -- none of that is exercised here. That's
  a materially different (and harder to build safely) kind of test.
- **No results.** Said above, worth repeating: nothing in this directory
  has ever actually run.
