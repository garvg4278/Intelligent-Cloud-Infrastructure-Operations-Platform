# ICOP — Intelligent Cloud Infrastructure Operations Platform

A cloud-native operations control plane: infrastructure provisioning,
deployment automation, observability, incident management, AI-assisted
analysis, analytics, notifications, and audit logging under one platform.

The browser-facing **Operations Console** is available at
http://localhost:8080 after startup. It provides account registration/sign-in,
live overview data, incident and alert visibility, audited environment
provisioning controls, and direct links to API docs and Grafana. It uses a
same-origin reverse proxy to the gateway; it does not bypass the platform's
JWT authentication.

**Status: Phase 5 (Breadth) complete — all ten services built and wired,
plus Terraform/Ansible/GitOps for real cloud provisioning. Phase 6's
security/performance hardening pass is also complete** (gateway-level
auth enforcement, caching, connection pooling, pagination, network
policies, image scanning — see ["Is this ready for production?"](#is-this-ready-for-production)
below and [ROADMAP.md](ROADMAP.md)'s Phase 6 for the full, honest list).
See [ROADMAP.md](ROADMAP.md) for exactly what's built vs. planned,
including honest caveats on Phases 2–6 — nothing in this repo has run
against a real Kubernetes cluster, a real Prometheus/Grafana instance, a
real (authenticated) LLM call, a real AWS account, or real production
traffic yet (read the caveats before trusting those paths blindly).
Nothing else in this README is aspirational — if it's described here, it
runs and is tested. **315 tests passing across ten services.**

## What's actually running right now

```
                    client
                      │
                      ▼
              ┌───────────────┐
              │  API Gateway  │   correlation IDs, rate limiting (Redis),
              └───────┬───────┘   error handling, metrics -- all on every route
                      │
                      ▼  routes /api/v1/* by service name to:

    Auth -- Deployment -- Alert -- Incident -- AI Ops
    Analytics -- Notification -- Audit -- Infrastructure
    (all nine real and tested)

    monitoring  -->  501 (not built yet, see ROADMAP.md)
```

Behind those nine boxes: **Deployment** hands work to a Celery worker
that shells out to `helm`/`kubectl` (needs a real cluster — bring your
own kubeconfig) and audits every trigger and rollback. **Alert** queries
Prometheus on a schedule (Celery Beat) and, when a rule newly breaches,
calls **Incident** to open a linked incident and **Notification** to
actually deliver it (webhook or email — alert no longer POSTs to
webhooks directly, see the alert README). **AI Ops** runs a real
tool-calling agent loop against Anthropic's API, querying Deployment/
Alert/Incident/Prometheus as tools — bring your own `ANTHROPIC_API_KEY`.
**Analytics** computes real statistics on the fly from Deployment/Alert/
Incident's data — no database of its own. **Audit** is an immutable
event log that five services now actually call, fifteen call sites in
all (see `services/audit/README.md` for the full list). **Infrastructure**
hands work to its own Celery worker that shells out to `terraform`/
`ansible-playbook` (needs a real AWS account — bring your own
credentials) to provision or destroy the actual EKS clusters
`terraform/environments/{staging,production}` define, then hands off to
`gitops/`'s ArgoCD config to keep every service's Kubernetes manifests in
sync with Git from there. **Prometheus** scrapes `/metrics` from all ten
services; **Grafana** reads from Prometheus. Every database-backed
service shares one Postgres instance (separate tables, real Alembic
migrations) and RabbitMQ carries deployment, alert-evaluation, and
infrastructure-provisioning jobs.

## Is this ready for production?

Asked directly, worth answering directly: **no, not without doing the
things listed under "What this doesn't cover" below first** — true
before Phase 6's hardening pass, and its follow-up pass, and still true
after both. What changed is which gaps are still open — including one
the follow-up pass found that was more serious in practice than most of
what the first pass fixed.

**What's real now, not just claimed:**
- **Authentication is actually enforced.** Every route under `/api/v1/*`
  (except register/login/refresh) requires a valid, unexpired token,
  checked by the gateway before anything is forwarded downstream. This
  wasn't true before Phase 6 — the gateway forwarded requests regardless
  of whether the Authorization header held anything valid, and no
  downstream service checked either.
- **The five Celery worker/beat processes that actually do the work are
  now part of `gitops/`.** Before the follow-up pass, `gitops/` only ever
  deployed the 10 API containers — a real cluster deployed through this
  repo's GitOps would have accepted every deployment trigger, alert
  evaluation, notification, and infrastructure request and then done
  nothing with any of them, forever, since nothing was consuming the
  queue. This was a bigger gap in practice than several of the named
  security items, and it was found by re-auditing, not reported by
  anything failing loudly.
- **Liveness and readiness probes actually check different things now.**
  Both used to hit the same shallow endpoint platform-wide — a database
  outage would neither restart a broken pod nor stop routing real traffic
  to it. The eight database-backed services now have a real `/health/ready`
  that pings the database; liveness stays deliberately shallow (checking
  a dependency there would restart every pod at once during an outage,
  which fixes nothing).
- **Security**: security headers on every response, an explicit CORS
  allow-list, Kubernetes `NetworkPolicy` segmentation (on by default),
  container image scanning in CI (Trivy, CRITICAL/HIGH fails the build),
  secrets generated and stored in AWS Secrets Manager (never hardcoded),
  and a request body size limit (neither FastAPI nor uvicorn enforce one
  by default).
- **Performance**: the one endpoint that fanned out to three other
  services on every request (`/analytics/overview`) is now cached; every
  list endpoint that had no limit (`deployments`, `incidents`, `alerts`,
  `audit/events`) is now paginated and capped; every database connection
  pool was raised off SQLAlchemy's untouched defaults.
- **Availability/resilience**: a `PodDisruptionBudget` now stops a node
  drain or autoscaler scale-down from taking every replica of a service
  out at once; the gateway's rate limiter fails open instead of taking
  down all traffic if Redis becomes unreachable (it used to fail closed —
  a Redis blip meant every request 500'd, not just rate-limited ones).

**What this doesn't cover, said plainly:**
- **No load test has ever been run.** `load-test/k6/baseline.js` is real
  and correct as far as careful reading and syntax-checking can confirm,
  but it has never executed against a running system — there is no
  number anywhere in this repo for requests/second, p95 latency under
  load, or a breaking point, because none has been measured.
- **No penetration test, no OAuth/SSO, no per-resource authorization**
  (today's check is "does this caller have a valid token," not "is this
  specific operator allowed to touch this specific cluster"), **no
  egress network restrictions** (only inbound traffic is segmented),
  **no service mesh or mTLS** between services.
- **No in-cluster Kubernetes RBAC for the workers that need it.** IRSA
  (Phase 5) grants AWS API permissions; it grants nothing for talking to
  the Kubernetes API server itself, which is what `deployment-worker`
  running `kubectl`/`helm` against its own cluster actually needs. Not
  built — see `gitops/values/services/deployment-worker.yaml`'s own note.
- **Terraform/Ansible/GitOps have never applied against a real AWS
  account.** Everything in `terraform/`, `ansible/`, and `gitops/` is
  real HCL/YAML, checked as thoroughly as possible without a cloud
  account or network access (see each directory's README) — not the same
  thing as having actually run.
- **One shared Postgres instance** is a real scaling ceiling once several
  services are each running several replicas — raising each pod's
  connection pool (done) doesn't fix the aggregate connection budget; a
  pooler in front of Postgres (RDS Proxy or PgBouncer) is the actual next
  step and isn't built.
- **The gateway forwards a verified identity as `X-ICOP-User`/`X-ICOP-Role`
  headers; no downstream service reads them yet.** Every audit record
  still says `actor: "system"`, not a real user.

See [ROADMAP.md](ROADMAP.md)'s Phase 6 for the full audit this section
summarizes, including exactly what was found and fixed across both
passes.

## Quickstart

```bash
cp .env.example .env
docker compose up --build
```

On PowerShell, use:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

- Gateway: http://localhost:8000 (docs at `/docs`)
- Operations Console: http://localhost:8080
- Auth: :8001 · Deployment: :8002 · Incident: :8003 · Alert: :8004 ·
  AI Ops: :8005 · Analytics: :8006 · Notification: :8007 · Audit: :8008 ·
  Infrastructure: :8009
- Prometheus: http://localhost:9090 (check **Status → Targets** — all 11 targets, the ten APIs plus Prometheus itself, should be UP)
- Grafana: http://localhost:3000 (`admin`/`admin`, dashboard auto-loaded)

The deployment worker needs a real cluster to do anything past "accepted
the request" (mount a kubeconfig in `docker-compose.yml`). The
infrastructure worker needs real AWS credentials to do anything past the
same point — set `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in `.env`,
or it fails cleanly at `terraform init` with the real error recorded (see
`services/infrastructure/README.md`). The AI Ops service needs
`ANTHROPIC_API_KEY` set in `.env` for `/ai/explain` to do anything past a
`503`. The notification service's `email` channel needs `SMTP_HOST` set;
`webhook` works with no configuration.

## Try it: alert fires → incident opens → ask AI Ops → check analytics

```bash
# 1. Register + log in
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "supersecret1"}'
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=you@example.com&password=supersecret1" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"
# Every call from here on needs -H "$AUTH" -- register/login/refresh are
# the only three routes that don't (see services/gateway/app/security.py).
# Without it, every one of the following gets a 401, not whatever this
# comment originally said it would do.

# 2. Create an alert rule against a metric that's actually being scraped
curl -X POST http://localhost:8000/api/v1/alerts/rules \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name": "gateway error rate", "service_name": "gateway",
       "metric_query": "rate(http_requests_total{job=\"gateway\",status=~\"5..\"}[5m])",
       "comparison": "gt", "threshold": 0.1, "severity": "critical",
       "webhook_url": "https://webhook.site/your-url"}'

# 3. Trigger evaluation right now instead of waiting for the 30s beat schedule
curl -X POST -H "$AUTH" http://localhost:8000/api/v1/alerts/rules/<rule_id>/evaluate

# 4. If it breached: check the alert (now linked to an incident)
curl -H "$AUTH" http://localhost:8000/api/v1/alerts
curl -H "$AUTH" http://localhost:8000/api/v1/incidents

# 5. Ask AI Ops -- it queries deployments/alerts/incidents/metrics itself
curl -X POST http://localhost:8000/api/v1/ai/explain \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"service_name": "gateway", "question": "why is the error rate high?"}'

# 6. Real statistics, computed from what's actually happened so far -- the
#    second identical call in a row is served from cache (Phase 6), not
#    recomputed; see services/analytics/app/cache.py
curl -H "$AUTH" "http://localhost:8000/api/v1/analytics/overview?service_name=gateway"
curl -H "$AUTH" "http://localhost:8000/api/v1/analytics/overview?service_name=gateway"

# 7. Send a notification directly too, if you want (step 3 above already
#    triggered one automatically, via the alert -> notification integration)
curl -X POST http://localhost:8000/api/v1/notifications \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"channel": "webhook", "target": "https://webhook.site/your-url",
       "subject": "Test", "body": "Hello from ICOP"}'

# 8. Check the audit trail -- steps 1-3 above already generated real
#    events (user.registered, user.login, alert_rule.created, and
#    deployment.* / alert.acknowledged if you triggered a deployment or ack'd).
#    Paginated since Phase 6 -- defaults to the 50 most recent, ?limit=
#    and ?offset= page through the rest.
curl -H "$AUTH" http://localhost:8000/api/v1/audit/events

# 9. Try the infrastructure service -- without real AWS credentials in
#    .env, this enqueues, runs `terraform init`, and fails cleanly at "no
#    valid credential sources", recorded as provision_failed with the
#    real error rather than hanging or crashing (same "bring your own
#    credentials, fail clean without them" pattern as step 5's
#    ANTHROPIC_API_KEY and the deployment worker's kubeconfig)
curl -X POST http://localhost:8000/api/v1/infrastructure/environments \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"environment_type": "staging"}'
curl -H "$AUTH" http://localhost:8000/api/v1/infrastructure/environments

# Anything not built yet is honest about it
curl -H "$AUTH" http://localhost:8000/api/v1/monitoring/list
# -> 501 {"detail": "'monitoring' service is not implemented yet.", "planned_for": "...", "see": "ROADMAP.md"}
```

## Running tests

```bash
make test
```

All ten services' tests run entirely against in-memory substitutes —
SQLite, `fakeredis`, Celery's own eager/synchronous test mode, mocked
HTTP clients for every inter-service call, `subprocess` mocked for Helm/
kubectl/Terraform/Ansible, a scripted fake LLM for the agent loop, mocked
`smtplib` for email — so `make test` needs nothing running. **315 tests,
ten services, currently green** (27 auth + 47 gateway + 37 deployment +
24 incident + 40 alert + 29 aiops + 28 analytics + 28 notification + 21
audit + 34 infrastructure).

## Tech stack (what's actually wired up)

| Layer          | Tool                                                          |
|----------------|-----------------------------------------------------------------|
| API            | FastAPI, Pydantic v2                                            |
| Auth           | PyJWT, bcrypt, RBAC (admin/operator/developer/viewer), verified at the gateway on every request, not just at auth's own routes |
| Deployment     | Celery + RabbitMQ, Helm + kubectl (via `subprocess`)              |
| Infrastructure | Celery + RabbitMQ, Terraform + Ansible (via `subprocess`)          |
| Observability  | Prometheus (real scrape config), Grafana (real dashboard), `prometheus_client` on all 10 services |
| Alerting       | PromQL rule evaluation, webhook notifications, Celery Beat        |
| AI Ops         | Anthropic Messages API, real tool-use agent loop, 4 read-only tools |
| Notifications  | Webhook + SMTP email, retry with exponential backoff, `{{}}` templating |
| Data           | PostgreSQL (SQLAlchemy 2.0, Alembic migrations, tuned connection pools), Redis |
| Caching        | Redis-backed, fail-open, 30s TTL on analytics' cross-service aggregation endpoints |
| IaC            | Terraform (AWS: VPC/EKS/RDS/ElastiCache/S3/IRSA), Ansible (SSM-based node config) |
| GitOps         | ArgoCD (`ApplicationSet` per environment, ArgoCD-managed `kube-prometheus-stack`) |
| Security       | Gateway-enforced JWT auth, security headers, CORS allow-list, K8s `NetworkPolicy`, Trivy image scanning in CI |
| Availability   | Liveness/readiness probes, `PodDisruptionBudget`, HPA (`autoscaling.enabled`) |
| Local infra    | Docker Compose (20 services)                                      |
| CI             | GitHub Actions — lint (ruff) + test + image scan (Trivy) per service, plus `terraform validate`/`ansible-playbook --syntax-check`, on push/PR |

`terraform/`, `ansible/`, and `gitops/` are real, but — like the Helm
chart and Prometheus/Grafana config before them — have never run against
something real end-to-end; see each directory's own README and
ROADMAP.md's Phase 5 for the exact caveats. Genuinely still just planned:
the two smaller deferred items noted in ROADMAP.md's "Immediate next
steps" (wiring a real IRSA role ARN through to the GitOps values, and the
next audit-coverage additions).

## Project layout

```
icop-platform/
├── services/
│   ├── gateway/       # routing, rate limiting, correlation IDs, metrics
│   ├── auth/           # users, JWT, RBAC
│   ├── deployment/     # state machine, Celery worker, Helm/kubectl
│   ├── incident/       # status lifecycle + timeline
│   ├── alert/          # rule evaluation, dedup, webhook, incident linking
│   ├── aiops/           # tool-calling agent: deployments/alerts/incidents/metrics -> LLM
│   ├── analytics/       # stateless aggregation over the other services' data
│   ├── notification/    # webhook + email delivery, retries, templating
│   ├── audit/            # immutable event log
│   └── infrastructure/    # state machine, Celery worker, Terraform/Ansible
├── terraform/
│   ├── bootstrap/       # apply once by hand: remote state S3 bucket
│   ├── modules/          # network, eks, rds, elasticache, object_storage, irsa
│   └── environments/      # staging, production
├── ansible/
│   ├── inventory/        # amazon.aws.aws_ec2 dynamic inventory (SSM-based, no SSH)
│   ├── roles/             # baseline, node_exporter
│   └── playbooks/
├── gitops/
│   ├── bootstrap/        # helm install argocd itself (the one imperative step)
│   ├── root/               # app-of-apps: ApplicationSets, AppProject, observability
│   └── values/              # per-environment + per-service Helm values
├── load-test/
│   └── k6/                 # baseline.js -- written, never run (see its README)
├── infra/
│   ├── helm/service-chart/   # one generic chart, every service
│   ├── prometheus/            # scrape config
│   └── grafana/                # datasource + dashboard provisioning
├── docker-compose.yml   # 20 services
├── Makefile              # make up / make test / make lint
├── .github/workflows/ci.yml
├── ROADMAP.md
└── README.md              # this file
```

## Known simplifications (see ROADMAP.md for the full list)

- **Seven things were never run against something real end-to-end:** the
  Helm chart/`HelmOrchestrator` (no cluster available), the Prometheus
  scrape config/Grafana dashboard (no live instance available), an
  authenticated AI Ops LLM call (no API key available), Terraform,
  Ansible, and GitOps (no AWS account and no network access at all were
  available — not even to download a Terraform provider plugin), and now
  the k6 load-test script (no running deployment to point it at). All
  seven are tested/checked as thoroughly as possible short of that — see
  each one's README for exactly what does and doesn't prove, and
  `.github/workflows/ci.yml`'s `validate-infra` and `image-scan` jobs for
  where the real `terraform validate`/`ansible-playbook --syntax-check`/
  Trivy now actually run (a GitHub Actions runner has the network access
  this sandbox didn't). Alembic migrations, by contrast, *were* fully
  verified against a real (if not Postgres) database for every service
  that has one.
- **Audit coverage is real but not exhaustive:** fifteen call sites
  across five services (see `services/audit/README.md`), not every
  mutating action in the platform. Role changes (no role-update endpoint
  exists yet to audit) and notification delivery outcomes are the more
  obvious remaining gaps.
- **Postgres is one shared instance** across every service with a
  database (separate tables) rather than physically separate databases.
  Each service's own connection pool was tuned (Phase 6), but that fixes
  single-pod throughput, not the aggregate connection ceiling once
  several services each run several replicas against this one instance —
  a pooler in front of Postgres (RDS Proxy or PgBouncer) is the actual
  next step for that and isn't built.
- **No flapping protection** on alert rules, **no escalation** — see the
  alert service's README.
- **AI Ops only implements Anthropic**; **notification only implements
  webhook + SMTP email** — both behind a `Protocol`, so a new provider or
  channel is one new implementation, not a rewrite.
- **Authentication is enforced (Phase 6); fine-grained authorization is
  not.** The gateway verifies every request has a valid token — it does
  not, and was never meant to, check whether the specific caller is
  allowed to do the specific thing they're asking for (deploy this
  service, provision this environment). That's each downstream service's
  own unbuilt concern; today every valid token can call everything.
- **NetworkPolicy segmentation is namespace-level, ingress-only.** Traffic
  from outside an `icop-{env}` namespace (or the observability namespace)
  is blocked; traffic between two services that have no legitimate reason
  to talk to each other, within the same namespace, is not — and nothing
  restricts outbound (egress) traffic at all. See
  `infra/helm/service-chart/templates/networkpolicy.yaml`'s own comments
  for the reasoning.
- **Terraform provisions this platform's own infrastructure, not
  "an environment for a user's app."** Exactly two environment types
  (staging, production), matching the two real directories under
  `terraform/environments/` — see `terraform/README.md` and
  `services/infrastructure/README.md` for what a more general,
  multi-tenant version of this would need that isn't built here.
- **Every `repoURL` in `gitops/` and `terraform/environments/*/backend.tf`
  is a placeholder** (`YOUR_ORG/icop-platform.git`, an unclaimed S3
  bucket name) — this repo doesn't have a real Git remote or a real AWS
  account behind it yet. See `gitops/README.md` for the exact bootstrap
  order once it does.
