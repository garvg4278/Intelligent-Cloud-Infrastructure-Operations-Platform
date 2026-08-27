# Analytics Service

Turns raw records from the deployment, incident, and alert services into
real statistics — computed on the fly from live data, not stored or
cached. No database of its own.

## Endpoints

All four take `service_name` as a required query param.

| Method | Path                    | Returns                                              |
|--------|--------------------------|--------------------------------------------------------|
| GET    | `/analytics/deployments`| total, success rate, by-status breakdown, deploy frequency |
| GET    | `/analytics/incidents`   | total, by-status/severity, mean time to resolution      |
| GET    | `/analytics/alerts`      | total, by-severity/status, noisiest rules (top 5)        |
| GET    | `/analytics/overview`    | all three combined                                       |

## Why no database

Every number here is derived from records that already live in the
deployment/incident/alert services' own Postgres tables. Storing a copy
here would mean either it goes stale or this service needs its own sync
logic — recomputing from the source on every request is simpler and
always current. Trade-off: this service is only as fast as its three
upstream calls, and only as available as all three of them (see below).

## Two different failure-handling choices, on purpose

- `GET /analytics/deployments` / `/incidents` / `/alerts` (single source
  each): if that one upstream service is unreachable, the endpoint
  returns a clean `503` — there's nothing partial to return.
- `GET /analytics/overview` (three sources): each section is fetched
  independently, and a single source failing doesn't blank out the other
  two — that section's value becomes `{"error": "..."}` and the response
  is still `200`. One upstream having a bad moment shouldn't hide data
  you do have. `test_overview_degrades_one_section_independently_on_failure`
  covers this directly.

## What's actually computed vs. what isn't

Built from what the other services actually track: deployment success
rate and frequency, incident mean-time-to-resolution, alert volume and
noisiest rules. **Not** built: "uptime %" and "resource utilization,"
both mentioned in the original design — the former would need Prometheus
range queries (only instant queries exist elsewhere in this repo) and the
latter would need CPU/memory metrics nothing here currently emits.
Better to leave both out than compute a number that doesn't mean what it
claims to.

## Run standalone

```bash
pip install -r requirements.txt
export DEPLOYMENT_SERVICE_URL=http://localhost:8002
export INCIDENT_SERVICE_URL=http://localhost:8003
export ALERT_SERVICE_URL=http://localhost:8004
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
pip install -r requirements.txt
pytest
```

19 tests: 9 on the pure aggregation math (using data shaped exactly like
the real services' JSON output — checked directly against
`DeploymentOut.model_dump_json()`, not guessed), 7 on the API layer with
faked upstream clients, 3 on the real HTTP clients' request/response
handling.
