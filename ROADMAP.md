# Roadmap

This reflects the actual, current state of the repo — not the end-state
vision. If something below isn't checked off, it does not exist in this
codebase yet, no matter how completely it might be described elsewhere.

## Phase 1 — Foundation (built)

- [x] Monorepo structure; `docker-compose.yml` for local Postgres, Redis,
      RabbitMQ
- [x] API Gateway — versioned routing (`/api/v1/*`), correlation IDs,
      Redis-backed rate limiting, centralized error handling
- [x] Auth Service — registration, login, JWT access/refresh tokens, RBAC
      (`admin` / `operator` / `developer` / `viewer`), protected routes
- [x] CI: lint (ruff) + test on every push/PR, for each service
      independently
- [x] Test suites across all five services — 97 tests total (see Phase 3
      for the breakdown), all running against in-memory substitutes
      (SQLite, `fakeredis`, mocked HTTP) so `make test` needs nothing
      running
- [x] Alembic migrations, across all four services with a database (auth,
      deployment, incident, alert) — scaffolded with the real `alembic`
      CLI, `env.py` reads `DATABASE_URL` from each service's own
      `Settings` as the single source of truth, and every one was
      verified against a real SQLite DB: schema matches
      `Base.metadata.create_all()` exactly, the app functions correctly
      against a migrated DB, `downgrade base` cleanly tears down, and
      `upgrade head` run twice is a correct no-op. Not verified against
      live Postgres specifically (none was available), but every column
      type used was already chosen to be portable across both. This is
      the one piece of infra work in this whole repo that got a full,
      real verification loop rather than a documented caveat.
- [ ] Per-resource permission checks — RBAC today is "can/can't call this
      endpoint," not "can this operator touch this specific cluster"
- [ ] Gateway-level JWT verification (currently only the auth service
      itself checks tokens; worth adding once there's a second protected
      downstream service)

## Phase 2 — Core Deployment Loop (built, with two honest caveats below)

The heart of the platform: one deployment path, fully real end to end.

- [x] Deployment service: `pending -> deploying -> health_checking ->
      succeeded` / `rolling_back -> rolled_back / failed` state machine,
      backed by Postgres
- [x] `HelmOrchestrator` — real `helm upgrade --install` /
      `kubectl rollout status` / `helm rollback` invocations via
      `subprocess`, behind an `Orchestrator` protocol so the state
      machine is fully testable without a cluster
- [x] Automatic rollback to the last known-good revision when a
      post-deploy health check fails
- [x] RabbitMQ actually in use — deploy jobs run on a Celery worker
      instead of blocking the HTTP request; the API returns `202` and the
      caller polls `GET /deployments/{id}`
- [x] Generic Helm chart (`infra/helm/service-chart`) used to deploy any
      ICOP service, with liveness/readiness probes wired to the `/health`
      endpoint every service already exposes
- [x] Gateway wired to actually proxy `/api/v1/deployments*` instead of
      stubbing it
- [ ] **Caveat 1:** `HelmOrchestrator`'s command construction and
      result-handling is unit-tested with `subprocess` mocked
      (`services/deployment/tests/test_orchestrator.py`), but it has
      never run against a real cluster — none was available while
      building this. Verify against a real (even local `kind`/`minikube`)
      cluster before trusting it further.
- [ ] **Caveat 2:** the Helm chart itself was never run through a real
      `helm lint`/`helm template` — no `helm` binary was reachable from
      the build sandbox (see `infra/helm/service-chart/README.md` for
      specifics and for the approximate structural check that was run
      instead). Run the real thing before trusting it.
- [ ] Manual rollback endpoint (`POST /deployments/{id}/rollback`) —
      today rollback only triggers automatically on a failed health check

## Phase 3 — Observability (built, with one honest caveat below)

- [x] HTTP metrics on all five services — `http_requests_total` and
      `http_request_duration_seconds`, labeled by ROUTE TEMPLATE (not raw
      path, which would blow up label cardinality) and always recorded
      even on a 429 or an unhandled 500, not just the happy path
      (verified with tests, see each service's `test_metrics_*` cases)
- [x] Real Prometheus scrape config (`infra/prometheus/prometheus.yml`)
      targeting all five services' `/metrics`
- [x] Real Grafana dashboard (`infra/grafana/dashboards/icop-overview.json`)
      — request rate, error rate, P95 latency, status-code breakdown,
      up/down — every panel built from a metric that's actually emitted
- [x] Alert service: rule evaluation against Prometheus (`PrometheusMetricsSource`,
      real PromQL queries), deduplication (one alert per breach, not one
      per evaluation cycle), auto-resolve when the metric recovers,
      webhook notification channel, Celery Beat for periodic evaluation
      — 28 tests
- [x] Incident service: enforced status-transition graph (`open ->
      acknowledged -> investigating -> mitigated -> resolved -> closed`,
      with reopen support), full timeline of status changes + comments —
      11 tests
- [x] Alert service creates a linked incident when a new alert fires
      (`HttpIncidentClient`), with webhook/incident failures each
      independently logged rather than losing the alert itself
- [x] Gateway wired to proxy `/api/v1/alerts*` and `/api/v1/incidents*`
      for real — 97 tests passing across all five services now
      (16 auth + 21 gateway + 21 deployment + 11 incident + 28 alert)
- [ ] **Caveat:** neither Prometheus's scrape config nor the Grafana
      dashboard has been loaded into a real running instance — no
      Prometheus/Grafana was available in the build sandbox. Every
      YAML/JSON file parses and every PromQL query references a real
      metric name (cross-checked by hand against the middleware code),
      but that's not the same as a live query engine confirming the
      queries actually run. See `infra/README.md`. `docker compose up`
      and checking `:9090/targets` + `:3000` closes this gap in minutes.
- [ ] No "Monitoring Service" as its own thing — the alert service's
      Prometheus-querying covers the threshold-evaluation piece of what
      it would have done; "service health views" / "health summaries"
      are not built
- [ ] No flapping protection on alert rules (a `for: 5m`-style "breach for
      N consecutive evaluations before firing") — a single noisy spike
      fires and immediately resolves
- [ ] No escalation for unacknowledged alerts/incidents

## Phase 4 — AI Ops MVP (built, with one honest caveat below)

- [x] Real tool-calling agent loop (`services/aiops/app/agent.py`)
      against Anthropic's Messages API — not a single prompt with pasted
      context. Bounded at `MAX_AGENT_ITERATIONS` (default 6) so a model
      that never stops requesting tools can't loop forever.
- [x] Four READ-ONLY tools, each a real HTTP call to a service already
      built in this repo: `get_recent_deployments`, `get_recent_alerts`,
      `get_recent_incidents`, `query_current_metric` (real PromQL against
      Prometheus). No tool can deploy, roll back, or change anything —
      that's the actual enforcement of the original design's "must not
      blindly act" rule, not just a comment saying so.
- [x] Every answer returns its full evidence trail (every tool called,
      its input, its result) alongside the text — the "explainable
      outputs" requirement, satisfied structurally, not asserted
- [x] A tool failing (a downstream service down, a bad PromQL query) is
      handed back to the model as a result, not raised — one bad tool
      call doesn't crash the whole request
- [x] Past queries logged (`AIQuery` table) and browsable via
      `GET /ai/history` / `GET /ai/history/{id}`
- [x] `ANTHROPIC_API_KEY` is bring-your-own — the service starts and
      `/health`, `/metrics`, `/ai/history` all work without one; only
      `POST /ai/explain` needs it, and returns a clear `503` naming the
      problem if it's missing rather than a stack trace
- [x] Gateway wired to proxy `/api/v1/ai/*` for real — 125 tests passing
      across all six services now (16 auth + 23 gateway + 21 deployment +
      11 incident + 28 alert + 26 aiops)
- [ ] **Caveat:** no API key was available in the build sandbox, so no
      *authenticated* call to a real model happened. What did happen: an
      actual request — with the real 4-tool schema attached — was sent to
      the live `api.anthropic.com` with an invalid key, and got back
      `401 authentication_error`, not a `400` about a malformed field.
      That means the real API validated the request shape (model,
      messages, tools) before ever checking the key — stronger evidence
      than a mock alone gives, though still short of confirming a real
      model produces a good answer with this tool set. See
      `services/aiops/README.md` for the exact verification done.
- [ ] Only Anthropic implemented (`LLMClient` is a Protocol; OpenAI/local
      would be a second `send()` implementation, not a rewrite)
- [ ] No streaming — `/ai/explain` blocks until the full answer is ready

## Phase 5 — Breadth (complete: services, Terraform, Ansible, and GitOps all built, with honest caveats)

- [x] **Analytics service** — real aggregation (deployment success rate
      and frequency, incident mean-time-to-resolution, alert volume and
      noisiest rules) computed on the fly from the deployment/incident/
      alert services' actual data. No database of its own — deliberately
      stateless, see the service's README for why. `/overview` degrades
      per-section on a single upstream failure rather than failing the
      whole request; the three single-source endpoints return a clean
      `503` instead, since there's nothing partial to return for one
      source. 19 tests.
- [x] **Notification service** — split out from the alert service per the
      original design's explicit principle ("notifications are async and
      failure-prone... should not be mixed into business logic"). Two
      real channels (webhook, SMTP email — the latter only registered if
      `SMTP_HOST` is configured), real retry logic with exponential
      backoff (dependency-injected sleep, so the retry logic itself is
      unit-tested without any test waiting through backoff), `{{key}}`
      template rendering, every delivery attempt tracked. 25 tests.
- [x] **Audit service** — immutable event log. "Immutable" is enforced,
      not just documented: there is no `PUT`/`PATCH`/`DELETE` route
      anywhere in the service, and a test asserts this at the HTTP level
      (405s, plus the record proven byte-for-byte unchanged) rather than
      just trusting no one adds one later. 13 tests.
- [x] Gateway wired to proxy all three for real — 27 gateway tests at
      that point (186 tests total, across all nine services, before the
      two integrations below were added — see the final count below).
- [x] Fixed a real gap noticed while touching the gateway for this phase:
      `/api/v1/infrastructure/*` (Infrastructure Service, section 6.4 of
      the original design — Terraform/Ansible/GitOps provisioning) had
      never been registered as a 501 stub in ANY phase, going back to
      Phase 1 — it just silently 404'd instead of getting the same honest
      "not built yet, here's the phase" response as everything else
      undone. Fixed now, not because it's newly undone (it isn't — still
      entirely unbuilt) but because leaving it inconsistent once noticed
      would undercut the whole "every gap is either real or honestly
      flagged" premise this repo is built on.
- [x] **Alert → notification wired for real.** `HttpNotificationClient`
      (`services/alert/app/notifier.py`) replaced the direct-webhook
      `WebhookNotifier` — a firing alert now goes through
      `POST {notification-service}/notifications` (channel="webhook",
      target=the rule's `webhook_url`) instead of being POSTed to
      directly. The `Notifier` protocol's shape didn't change, so
      `executor.py`'s firing/dedup/resolve logic needed zero changes;
      only what `get_notifier()` constructs by default did.
- [x] **Real audit events — broadened to nine call sites across four
      services.** `auth` emits `user.registered`/`user.login` (with the
      real user's email as actor — the one service with an actual
      identity to attribute something to); `deployment` emits
      `deployment.triggered` on every create, then exactly one of
      `deployment.succeeded`/`deployment.rolled_back`/`deployment.failed`;
      `incident` emits `incident.created` and `incident.status_changed`
      (with before/after status — the specific gap this file used to
      flag by name); `alert` emits `alert_rule.created` and
      `alert.acknowledged`. Every call site is wrapped so a failure
      recording the event never breaks the action itself — all nine have
      an explicit `test_audit_failure_does_not_break_*` test proving
      this, not just asserting it in a docstring. **223 tests passing
      across all nine services now** (24 auth + 27 gateway + 33
      deployment + 20 incident + 36 alert + 26 aiops + 19 analytics + 25
      notification + 13 audit).
- [ ] Still not exhaustive: role changes (no role-update endpoint exists
      yet to audit) and notification delivery outcomes are the more
      obvious remaining gaps — see the audit service's README for the
      full current list.
- [x] Two more real gaps found and fixed while auditing the repo for this
      pass — same "leaving it inconsistent once noticed would undercut
      the whole premise" reasoning as the infrastructure-501-stub fix
      above: `.github/workflows/ci.yml` was checked off in Phase 1 as
      built but didn't actually exist in the repo (the `make test`/
      `make lint` targets it should have been calling did, and always
      worked locally — the workflow file itself was just missing); and
      `infra/prometheus/prometheus.yml` only scraped five of the nine
      services that actually expose `/metrics` (aiops, analytics,
      notification, and audit each had a working `MetricsMiddleware`
      since the phase that added them, just never a scrape target — this
      was cross-checked against each service's `main.py` before adding
      the target, not assumed from the service name). Both fixed now.
- [x] **Infrastructure service** — the ninth-turned-tenth service, and
      what `/api/v1/infrastructure/*` proxies to for real now instead of
      a 501. Same shape as the deployment service: a Protocol per
      external tool (`TerraformOrchestrator`, `AnsibleOrchestrator`), a
      pure `executor.py` state machine with no Celery import, every
      transition audited (six new call sites — see the audit service's
      README). `POST /environments {"environment_type": "staging"}`
      drives `terraform apply` then `ansible-playbook` against a real EKS
      cluster; `DELETE /environments/{id}` drives `terraform destroy`. 31
      tests, all against mocked `subprocess.run` — see
      `services/infrastructure/README.md` for exactly what that does and
      doesn't prove, and for why a failed Ansible run doesn't
      auto-destroy the Terraform-provisioned infrastructure underneath it.
- [x] **Terraform** (`terraform/`) — real AWS provider HCL for two
      environments (staging, production), matching docker-compose's
      topology: `network` (VPC/subnets/NAT), `eks` (cluster + managed
      node group + OIDC provider for IRSA), `rds` (Postgres, parity with
      the `postgres:16-alpine` container), `elasticache` (Redis, parity
      with `redis:7-alpine`), `object_storage` (S3, for the artifacts the
      original design describes), `irsa` (pod-scoped AWS permissions, no
      static credentials anywhere). A `bootstrap/` module for the
      remote-state S3 bucket itself, meant to be applied once by hand —
      the classic chicken-and-egg where a state backend can't create the
      very bucket it stores its own state in.
- [x] **Ansible** (`ansible/`) — post-provision node configuration,
      reached entirely over AWS Systems Manager Session Manager (no SSH
      keypair, no bastion host, no port 22 open anywhere — see the EKS
      module's `AmazonSSMManagedInstanceCore` policy attachment).
      `baseline` role verifies (never installs — EKS's own AMI bootstrap
      already did) that containerd/kubelet are running, and sets
      consistent timezone/NTP across nodes; `node_exporter` role installs
      host-level metrics collection as a systemd service.
- [x] **GitOps** (`gitops/`) — ArgoCD `ApplicationSet`s (one per
      environment, not one resource matrixed over both) deploying every
      ICOP service from the existing `infra/helm/service-chart`. Staging
      auto-syncs on every merge; production deliberately has no
      `syncPolicy.automated` block at all — promoting to production is a
      human running `argocd app sync`, encoded as a genuinely different
      resource rather than a boolean flag pretending the two policies are
      the same shape. Also closes a loop the IRSA work opened: the shared
      Helm chart gained a `serviceAccount.create`/`annotations` values
      block (and the template/helper to go with it) so a real IRSA role
      ARN can actually be attached to a pod — checked against the chart's
      own offline render-checker, not just written and assumed correct.
- [x] **256 tests passing across all ten services now** (24 auth + 29
      gateway + 33 deployment + 20 incident + 36 alert + 26 aiops + 19
      analytics + 25 notification + 13 audit + 31 infrastructure).
- [ ] None of terraform/ansible/gitops has run against a real AWS account
      or cluster — no network access at all was available in the sandbox
      this was built in, not even to download a Terraform provider
      plugin. See each directory's own README for exactly what was
      checked offline instead (structural balance/cross-reference
      scripts, not `terraform validate`/`ansible-playbook --syntax-check`
      themselves) and `.github/workflows/ci.yml`'s new `validate-infra`
      job, which runs the real versions of both — on a GitHub Actions
      runner with real network access, once this repo has a real Git
      remote for that workflow to trigger against.
- [ ] `terraform/environments/*/backend.tf` and every ArgoCD
      Application/ApplicationSet still hold placeholder values (an
      unclaimed S3 bucket name, `YOUR_ORG/icop-platform.git`) that only
      resolve once this repo has a real cloud account and a real Git
      remote — see `terraform/README.md` and `gitops/README.md` for the
      exact bootstrap order.

## Phase 6 — Depth & Polish (hardening pass complete; rest not started)

Triggered by a direct question worth recording honestly: asked whether
this platform was "ready, with no reason to make changes," handled heavy
load, was scalable, and implemented "all" security features. The honest
answer was no on every count, and still is after this pass -- what
changed is that the gaps are now smaller, specific, and (mostly) closed
rather than general and open. What follows is what an actual audit
against those four questions found, and what was fixed.

### Security

- [x] **The gateway did not verify JWTs. Nothing downstream did either.**
      This was the single most serious finding of this pass, not a minor
      gap: `POST /api/v1/deployments` and `POST
      /api/v1/infrastructure/environments` (trigger a real Helm rollout;
      provision real AWS infrastructure) were both callable by anyone who
      could reach them, gateway included -- previously documented as "the
      gateway doesn't verify JWTs itself" without the follow-through that
      NO service did. Fixed for real: `services/gateway/app/security.py`
      verifies every request under `/api/v1/*` (except
      register/login/refresh) against the same HS256 secret auth signs
      with, locally -- not a network call to auth per request, which
      would have made the busiest service in the platform a second
      bottleneck. Verified past "it compiles": a standalone script
      exercised real forged-signature, expired-token, wrong-token-type,
      and payload-tampering cases against the actual cryptographic logic
      before it went in. What this does NOT do: per-role authorization
      (can THIS operator touch THIS cluster) -- that's still each
      downstream service's own unbuilt concern, now more precisely true
      of every service instead of just being an auth-service caveat.
- [x] Security headers (`X-Frame-Options`, CSP, HSTS, etc.) on every
      gateway response, including error responses --
      `services/gateway/app/middleware/security_headers.py`.
- [x] CORS: explicit allow-list (`CORS_ALLOWED_ORIGINS`), empty by
      default -- no frontend exists yet (see the root README) so the
      honest default is no cross-origin access, not a guessed dev URL.
      Never a wildcard combined with credentials, the well-known
      misconfiguration.
- [x] The rate limiter trusted `request.client.host` directly, which is
      wrong the moment a real load balancer sits in front of the gateway
      (every real user would appear as the LB's own IP, sharing one rate
      limit bucket). Fixed behind an explicit, default-off
      `TRUST_PROXY_HEADERS` setting -- see
      `services/gateway/app/middleware/rate_limit.py`'s `_client_ip` for
      why it defaults off (turning it on before a real proxy exists would
      let a client rate-limit-dodge by just claiming to be a different IP)
      and exactly when to flip it.
- [x] Network segmentation: `infra/helm/service-chart` gained a real
      `NetworkPolicy` template (default-deny ingress from outside the
      namespace, explicit allow for same-namespace traffic and the
      observability namespace's Prometheus) -- on by default in
      `gitops/values/environments/{staging,production}.yaml`. Named
      scope limit, not an oversight: this is namespace-level
      segmentation, not per-service-pair zero trust -- see the template's
      own comments.
- [x] Image scanning (`.github/workflows/ci.yml`'s new `image-scan` job,
      Trivy against every service's real Dockerfile, CRITICAL/HIGH fails
      the build) -- named in the original design's security controls,
      wasn't built until this pass.
- [x] Secrets management is real (Terraform's `random_password` +
      Secrets Manager for the RDS password, IRSA for pod-scoped AWS
      permissions with no static credentials) but is **not** the
      HashiCorp Vault the original design doc names -- a deliberate
      substitution for something more idiomatic to an AWS-based stack,
      not a gap being quietly passed off as the thing it isn't.
- [ ] **Not done, and worth naming plainly:** OAuth/SSO, per-resource
      RBAC (can this operator touch this specific cluster, not just call
      this endpoint), egress NetworkPolicies (only ingress is
      restricted), a service mesh or mTLS between services, and any real
      penetration test. None of these were attempted -- not a shallow
      version of any of them, nothing here should be read as "handled."

### Load, scale, and performance

- [x] Analytics computed every report live, on every request, with no
      caching -- `/analytics/overview` alone fanned out to three other
      services on every call. Under a dashboard polling every few
      seconds, multiplied across however many users had it open, that's
      load on deployment/incident/alert that scales with a THIRD PARTY's
      request rate, not just direct callers -- exactly the shape of thing
      that surprises people during a real traffic spike. Fixed with a
      Redis-backed, fail-open, 30-second cache
      (`services/analytics/app/cache.py`) that explicitly never caches a
      failed or partially-degraded result.
- [x] Every database-backed service used SQLAlchemy's untouched defaults
      (5 pool + 10 overflow = 15 connections per pod). Raised to 10+10=20
      across all eight services, plus a 30-minute connection recycle to
      avoid stale-connection errors under real traffic patterns. Honest
      tension documented, not hidden: raising per-pod pool size doesn't
      fix the AGGREGATE connection ceiling once several services are each
      running several replicas against the one shared Postgres instance
      -- a connection pooler (RDS Proxy or PgBouncer) is the actual next
      step for that, and isn't built here.
- [x] Four list endpoints (`deployments`, `incidents`, `alerts`, and
      `audit/events`) had no limit at all -- an unbounded query and an
      unbounded response, worst for `audit/events` specifically since
      "retain immutable history" / "stored forever" (this platform's own
      design principles) means that table has no natural ceiling. Every
      one of them now defaults to 50 rows, caps at 200 even if asked for
      more, and supports `offset` for real pagination.
- [x] No `PodDisruptionBudget` existed -- a node drain or cluster-
      autoscaler scale-down could have taken out every replica of a
      service at once with nothing to stop it. Added to the chart,
      on by default (unlike NetworkPolicy, a PDB can't break connectivity
      the way a misconfigured one could, so there's no equivalent reason
      to default it off).
- [x] A k6 load-test script now exists (`load-test/k6/baseline.js`) --
      real, authenticated traffic through the actual login flow, a
      read-heavy mix across several services, with think time.
- [ ] **What none of the above adds up to: a claim that this platform has
      been shown to handle heavy load.** The k6 script has never been run
      -- no running deployment was reachable from the sandbox any of this
      was built in (see the root README's caveats, same root cause as
      every other "written, never run" note in this repo). Every fix
      above is real and defensible on its own logic; none of them is a
      substitute for an actual measurement against an actual running
      system. Do that before repeating "handles heavy load" as a fact
      about this platform rather than a description of the code.

### Follow-up hardening (second pass)

Asked again, directly, whether anything else needed upgrading for
security/production/scalability. It did — the second pass through found
gaps the first one missed, one of them more serious in practice than
several of Phase 6's original findings:

- [x] **The five Celery worker/beat processes were never actually
      deployed to Kubernetes.** `gitops/`'s ApplicationSets only ever
      listed the 10 API containers -- `deployment-worker`, `alert-worker`,
      `alert-beat`, `notification-worker`, and `infrastructure-worker`
      (the processes docker-compose.yml actually runs to consume the jobs
      those APIs enqueue) had no Application at all. A real cluster
      deployed through this repo's GitOps would have accepted every
      deployment trigger, alert evaluation, notification, and
      infrastructure provisioning request and then done nothing with any
      of them -- everything would sit in RabbitMQ forever. Fixed:
      `infra/helm/service-chart` gained a `workload.type` (`webService` /
      `worker`) so a worker Deployment correctly has no Service and no
      HTTP probes (there's no HTTP server in a Celery worker to expose or
      probe), and all five now have real `gitops/values/services/*.yaml`
      entries in both ApplicationSets. Verified past "valid YAML": the
      actual rendered worker Deployment was checked to confirm it carries
      the real celery command and genuinely has no `ports`/`livenessProbe`/
      `readinessProbe` keys at all, not just empty ones.
- [x] **Found and fixed a real IRSA binding bug while in the area:** the
      Terraform trust policy expected a ServiceAccount literally named
      `deployment`; the GitOps values relied on the chart's own fallback,
      which would have created one named after the release
      (`icop-staging-deployment`) instead. This wouldn't have failed
      loudly -- the role ARN annotation would look correctly wired, but
      `AssumeRoleWithWebIdentity` would still fail its trust condition.
      Also relocated where the binding lives: onto `deployment-worker`
      (the process that actually shells out to helm/kubectl), not the
      stateless API pod that only enqueues Celery tasks.
- [x] **Liveness and readiness probes hit the exact same shallow
      `/health` endpoint, platform-wide.** A database outage would never
      restart a broken pod (liveness never failed) AND would never stop
      routing real traffic to it either (readiness never failed) — the
      two probes existing at all was providing none of their actual
      value. Fixed: all 8 database-backed services gained a real
      `/health/ready` that pings the database and returns 503 on
      failure, kept deliberately separate from the shallow `/health`
      liveness check (checking a dependency in a liveness probe would
      restart every pod at once during a DB outage, which fixes nothing
      and adds a restart storm on top of an existing problem — readiness
      failing is the correct response, since it just stops routing
      traffic to the one pod that can't serve it). gateway and analytics
      gained a `/health/ready` too, deliberately kept as a shallow alias
      of `/health` — neither has a single dependency whose outage should
      pull it from rotation (the rate limiter fails open now; analytics
      already degrades per-section), so a fake-deep check would have
      been dishonest rather than protective.
- [x] **The rate limiter had no failure handling.** A Redis outage meant
      every request through the gateway — not just rate-limited ones —
      failed with a 500. Fixed to fail open: a Redis error now logs and
      lets the request through unrate-limited rather than breaking the
      entire platform's traffic over what should be an auxiliary
      protection.
- [x] **No request body size limit existed anywhere.** Neither FastAPI
      nor uvicorn enforce one by default, and the gateway read every
      request body fully into memory before forwarding it, regardless of
      size. Fixed at the one chokepoint every request already passes
      through: a fast Content-Length pre-check plus a backstop on the
      actual body length (`MAX_REQUEST_BODY_BYTES`, 10 MB default) —
      the backstop matters because Content-Length can be absent or
      understated, not just because it's convenient.
- [x] Confirmed rather than assumed: every `httpx` call in the codebase
      already had an explicit timeout, including a correctly *longer*
      one (60s vs the usual 10s) for the one call that legitimately needs
      it — aiops' Anthropic API call. Checked, not fixed, because there
      was nothing to fix here.
- [ ] **What this pass didn't reach:** in-cluster Kubernetes RBAC for
      `deployment-worker` and `infrastructure-worker` (IRSA only grants
      AWS API permissions — actually running `kubectl`/`helm` against the
      cluster's own API server from inside a pod needs a
      ClusterRole/ClusterRoleBinding, which isn't built); the
      X-ICOP-User/X-ICOP-Role headers the gateway forwards are still
      unread by every downstream service, so every audit record still
      says `actor: "system"`; and — repeating Phase 6's own point,
      because it bears repeating rather than being quietly superseded by
      a longer list of fixes — none of this has been observed working
      against a real cluster. Every fix above is real and independently
      reasoned through; none of them is a substitute for watching it
      actually happen.

### Test count after both passes

**315 tests passing across all ten services** (27 auth + 47 gateway + 37
deployment + 24 incident + 40 alert + 29 aiops + 28 analytics + 28
notification + 21 audit + 34 infrastructure) — up from 286 (first
hardening pass) by 29: 3-4 new tests per service for the readiness/
liveness split (all ten services), plus gateway's own additional
coverage (fail-open rate limiting, request body size limits). Every
number in this file has been independently verified by grepping `def
test_`, not asserted — the same standard this file has held itself to
since Phase 1.

### Still genuinely not started (unchanged from before this pass)

- [ ] Integration/e2e tests (today's tests are unit/integration-with-mocks
      level, scoped to a single service)
- [ ] Self-healing rules
- [ ] Full documentation set — every service has its own README today
      (ten of them now), plus this file, the root README, and per-
      directory READMEs for terraform/ansible/gitops/load-test and two
      infra READMEs (Helm chart, Prometheus/Grafana). What's still
      missing is anything ABOVE the per-service level: no single runbook,
      no architecture diagram beyond the ones in these READMEs, no
      troubleshooting guide spanning multiple services.
- [ ] Stretch features: cost analyzer, predictive scaling

## Phase 7 — GitOps/Terraform/Ansible Audit (verification + targeted fixes)

Triggered by a direct request to check this repo's Terraform/Ansible/
GitOps for gaps and build forward, on the premise that those three were
the main thing still missing. Worth recording plainly: that premise
wasn't quite right. All three existed already, in real, reviewable form,
as of Phase 5/6 -- what this pass actually found, by reading the code
rather than trusting the premise or this file's own prior claims about
itself, was narrower and more specific than "build IaC from scratch."
Same network constraint as every prior pass: no AWS account, no `helm`/
`terraform`/`ansible`/`kubectl` binaries, no real cluster. Everything
below is either a structural/offline check or a fix reasoned through
against the actual code paths it touches, not something watched working.

### A real, sync-blocking bug found and fixed

- [x] **`gitops/root/resources/project.yaml`'s resource whitelists didn't
      cover everything the chart actually renders.**
      `podDisruptionBudget.enabled: true` is the chart's own default, and
      `networkPolicy.enabled: true` is set in both environment tiers --
      meaning both `PodDisruptionBudget` and `NetworkPolicy` render for
      every service, in both environments, always. Neither kind was in
      `namespaceResourceWhitelist`. As committed before this fix, every
      single Application sync would have failed on "resource kind not
      permitted in project" for both kinds, every time, in both
      environments -- not an edge case, the default path. Existing
      structural checks (`check_gitops_yaml.py`) parse YAML shape and
      Go-template field references; cross-referencing the AppProject's
      whitelist against what the chart's own templates actually render
      was a gap in the checking, not just the config. Fixed both the
      whitelist and the `AppProject`'s own description text, which
      still claimed a stale "would be flagged for review" for the
      resource kind (see next section) this same pass deliberately
      allowed.

### In-cluster Kubernetes RBAC for deployment-worker (closes part of a Phase 6 gap)

- [x] Phase 6 flagged this correctly but bundled two services into one
      bullet: "in-cluster Kubernetes RBAC for `deployment-worker` and
      `infrastructure-worker` ... isn't built." Reading
      `services/infrastructure/app/terraform_orchestrator.py` and
      `ansible_orchestrator.py` this pass found that's only half true --
      infrastructure-worker's code shells out to `terraform` and
      `ansible-playbook` only, both of which talk to AWS (via IRSA and
      AWS SSM respectively), never this cluster's own Kubernetes API. It
      doesn't need this and doesn't have it.
      `services/deployment/app/orchestrator.py`'s HelmOrchestrator does --
      real `helm upgrade`/`helm history`/`helm rollback`/`kubectl rollout
      status` calls. Built: `infra/helm/service-chart/templates/
      clusterrole.yaml` + `clusterrolebinding.yaml`, toggled via the new
      `clusterRbac.enabled` value, on only for `deployment-worker`.
- [x] **Why a ClusterRole and not a namespaced Role**, worth recording
      since it wasn't obvious going in: `services/deployment/app/
      executor.py` sets the Helm target namespace to
      `deployment.environment.value` -- literally `"staging"` /
      `"production"` -- which is a *different* namespace than
      `icop-staging`/`icop-production`, where this worker's own pod
      actually runs (and where `--create-namespace` on first deploy
      implies those bare-named namespaces don't necessarily exist yet
      either). A Role bound in the worker's own namespace has no
      mechanism to grant permissions over a namespace it doesn't live in
      and that may not exist at bind time; creating a Namespace at all is
      inherently cluster-scoped. Scoped narrowly given that constraint --
      see the template's own comments for the exact rule set and the
      reasoning behind each one (full CRUD only on what the chart itself
      renders plus Helm's own Secret-based release storage; read-only on
      Pods/ReplicaSets/Events; explicitly nothing under
      `rbac.authorization.k8s.io`).
- [ ] **A genuine open question this surfaced, not resolved here:** is
      the `staging`/`production` vs. `icop-staging`/`icop-production`
      namespace split (platform control plane vs. whatever the
      deployment service deploys on behalf of a caller) intentional
      design, or an unnoticed mismatch? The `--create-namespace` flag
      being meaningfully used (not redundant) is evidence for
      intentional. Nowhere documents it as a deliberate choice. Worth a
      real decision before this goes further -- it currently just works
      because the ClusterRole above was scoped defensively enough to
      cover either answer.

### Stale documentation found and fixed (no behavior change, just wrong claims)

- [x] `terraform/modules/irsa/README.md` said the Helm chart "does not
      have a `serviceAccount.annotations` value today" -- it has since
      Phase 5/6; the README was never updated after. Rewritten to
      describe the current real state, including the two items below.
- [x] `infra/helm/service-chart/values.yaml`'s own comment, and this
      file's own "Immediate next steps" item 2 (see below), both pointed
      at `gitops/values/services/deployment.yaml` -- the actual file is
      `deployment-worker.yaml`. Both fixed.
- [x] `infra/helm/service-chart/README.md`'s "What's in it" list covered
      only `Deployment`/`Service`/`HorizontalPodAutoscaler` --
      `ServiceAccount`, `NetworkPolicy`, and `PodDisruptionBudget` were
      added in earlier phases and never added to this list. The "how
      this was validated" section had the same lag: it named only three
      of the (now eight) templates `_approximate_render_check.py` covers.
      Both brought current.

### New tooling: closing the IRSA output hand-off loop

- [x] `terraform/scripts/apply_irsa_output.py` -- takes `terraform
      output -json`, extracts `deployment_irsa_role_arn`, and patches it
      into `gitops/values/services/deployment-worker.yaml` in place of
      the placeholder, via precise text substitution rather than a YAML
      parse+dump (which would silently strip that file's extensive
      comments). Refuses to overwrite a *different* real-looking ARN
      without `--force`, supports `--dry-run`, and ships a `--self-test`
      that exercises every path (replace, no-op re-apply, refusal,
      forced overwrite, both `terraform output -json` and plain-value
      input shapes) against a fabricated example -- no real terraform or
      AWS involved. Run and passing: `python3
      terraform/scripts/apply_irsa_output.py --self-test`. Also run
      end-to-end in `--dry-run` mode against the real
      `deployment-worker.yaml` in this repo, confirmed it correctly
      finds the real placeholder and correctly makes no change.
- [ ] **A real limitation this script does not fix, found while building
      it:** `deployment-worker.yaml` is one file, loaded by *both*
      ApplicationSets. Staging and production each get their own IAM
      role from their own `deployment_irsa` module instantiation
      (confirmed both `environments/staging/main.tf` and
      `environments/production/main.tf` define one), with different real
      ARNs -- but there's only one place in this repo to put "the"
      annotation value today. Running the script for the second
      environment overwrites the first environment's real ARN in that
      shared file (the script's refuse-without-`--force` behavior
      catches this rather than silently doing it, but can't make the
      file hold two values at once). Documented in the script's own
      docstring and in `terraform/modules/irsa/README.md`. Real fix,
      not done here: split into per-environment-per-service values
      files, or relocate just this one annotation into the
      environment-tier files and rely on Helm's per-key map merge.

### What this pass did NOT do

Did not run `terraform validate`, `ansible-lint`/`--syntax-check`,
`helm lint`, or anything against a real AWS account or cluster -- same
tooling/network constraint as every prior pass (confirmed again this
session: no `terraform`/`ansible`/`helm`/`kubectl` binaries and no
network egress in this sandbox either). Did not touch service
application code (the X-ICOP-User/X-ICOP-Role header gap Phase 6 named
is still open, audit actor is still always `"system"`), the Monitoring
Service stub, self-healing, or the frontend -- out of scope for what was
asked this pass, not forgotten.



`/api/v1/monitoring/*` is registered on the gateway — so the full API
surface from the original design is visible, versioned, and routable —
but it currently returns a structured `501 Not Implemented` naming the
phase it's planned for. `deployments`, `alerts`, `incidents`, `ai`,
`analytics`, `notifications`, `audit`, and now `infrastructure` used to
be on this list (or, for `infrastructure`, should have been from Phase 1
onward but wasn't registered at all until the pass noted in Phase 5
above) and now proxy to real services instead. `monitoring` is the one
name left on it. That's deliberate: an honest 501 is worth more than a
route that returns fabricated data, and worth more than hiding the
endpoint entirely.

## Immediate next steps (in order)

1. Ground every "written, never run for real" caveat in reality: `helm
   lint`/`helm template` the chart, exercise `HelmOrchestrator` against a
   real cluster, load the Prometheus config + Grafana dashboard into real
   instances, run an authenticated `/ai/explain` call against a real
   model with a real `ANTHROPIC_API_KEY` — and now the larger version of
   the same gap: apply `terraform/bootstrap` and
   `terraform/environments/staging` against a real AWS account, run
   `ansible-playbook playbooks/site.yml` against the real nodes that
   creates, and bootstrap `gitops/` against a real ArgoCD instance once
   this repo has a real Git remote for it to sync from. Still entirely
   ungrounded — Phase 7 added a fix and a script, not a real run.
2. The IRSA → Helm-chart hand-off now has a script
   (`terraform/scripts/apply_irsa_output.py`, Phase 7) — what's left is
   actually running it against a real `terraform apply` output, which
   depends on step 1 above happening first. Before that: decide the
   Phase 7 open question on whether staging and production sharing one
   `gitops/values/services/deployment-worker.yaml` is acceptable
   (documented workaround: `--force` plus accepting one environment's
   ARN gets overwritten) or worth actually restructuring first.
3. Decide the other Phase 7 open question: is the `staging`/`production`
   vs. `icop-staging`/`icop-production` namespace split (what
   `deployment-worker`'s ClusterRole is scoped around) intentional
   design or an unnoticed mismatch? Affects whether that ClusterRole is
   the right shape long-term or a wider-than-necessary stopgap.
4. Audit coverage is at fifteen call sites now; a role-update endpoint
   (auth doesn't have one yet) and notification delivery outcomes are the
   next plausible additions. Same status as before Phase 7 — not what
   this pass was scoped to.
5. No "Monitoring Service" as its own thing yet — still the one
   remaining 501 stub on the gateway (see the section above).
