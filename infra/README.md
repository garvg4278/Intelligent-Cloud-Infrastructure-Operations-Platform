# infra/

Configuration for the pieces of the platform that aren't themselves
FastAPI services: the Helm chart used to deploy every service
(`helm/service-chart`), and the observability stack (`prometheus/`,
`grafana/`).

## Prometheus

`prometheus/prometheus.yml` scrapes `/metrics` on all ten services
(gateway, auth, deployment, incident, alert, aiops, analytics,
notification, audit, infrastructure) every 15s. Every target in that file
is a service that genuinely exposes `http_requests_total` and
`http_request_duration_seconds` today (see `services/*/app/middleware.py`)
— nothing here points at a metric or a target that doesn't exist. Four
services (aiops, analytics, notification, audit) had a working
`/metrics` endpoint for a full phase before actually being added as
scrape targets here — a real gap, found and fixed while auditing the
repo for the Terraform/Ansible/GitOps pass (see ROADMAP.md's Phase 5).

## Grafana

`grafana/provisioning/` auto-configures Grafana on startup: one
Prometheus datasource, and one dashboard (`grafana/dashboards/icop-overview.json`)
covering request rate, error rate, P95 latency, status-code breakdown,
and per-service up/down — all five panels built from metrics that are
actually emitted, not placeholders.

**What was and wasn't validated:** no real Prometheus or Grafana instance
was running while this was built (same sandbox constraint as the Helm
chart — see `helm/service-chart/README.md`). What *was* checked: every
YAML/JSON file parses correctly, and every PromQL query in the dashboard
references a metric name that's grep-able in this repo's own middleware
code — cross-referenced by hand, not by an actual query engine, since
there's no live Prometheus here to ask "does this query even parse."
**Neither Prometheus's scrape config nor the dashboard has been loaded
into a real running instance.** `docker compose up` will actually do
that — check `http://localhost:9090/targets` for scrape health and
`http://localhost:3000` (default login `admin`/`admin`) for the
dashboard before trusting either one blindly.

## Run it

```bash
docker compose up --build
# Prometheus: http://localhost:9090  (Status -> Targets to confirm all 10 are UP)
# Grafana:    http://localhost:3000  (ICOP Overview dashboard, auto-loaded)
```
