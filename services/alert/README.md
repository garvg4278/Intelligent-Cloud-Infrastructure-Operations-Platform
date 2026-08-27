# Alert Service

Evaluates rules against Prometheus, fires + deduplicates + notifies +
links an incident when one breaches, and resolves it automatically when
the metric recovers.

## Endpoints

| Method | Path                            | Purpose                                     |
|--------|----------------------------------|------------------------------------------------|
| POST   | `/alerts/rules`                  | Create a rule                                   |
| GET    | `/alerts/rules`                  | List rules, filterable by `service_name`        |
| GET    | `/alerts/rules/{id}`             | Get one rule                                    |
| POST   | `/alerts/rules/{id}/evaluate`    | Evaluate one rule right now (202, async)         |
| POST   | `/alerts/evaluate-all`           | Evaluate every active rule right now (202, async)|
| GET    | `/alerts`                        | List alerts, filterable by `status_filter`/`severity` |
| GET    | `/alerts/{id}`                   | Get one alert                                   |
| POST   | `/alerts/{id}/acknowledge`       | Mark acknowledged (doesn't resolve it)          |

A Celery Beat schedule also calls `evaluate-all`'s underlying task every
`EVALUATION_INTERVAL_SECONDS` (default 30) automatically — the manual
endpoints exist for on-demand/demo use, not as the only way this runs.

## Evaluation pipeline

For each active rule: query `metric_query` (raw PromQL) against
Prometheus, compare the result to `threshold` using `comparison`
(`gt`/`gte`/`lt`/`lte`). Then:

- **Newly breached** (no alert already firing for this rule) → create the
  alert, deliver it via the notification service if `webhook_url` is set
  (see below — as of this pass, no longer a direct webhook POST), and
  call the incident service to open a linked incident
- **Still breached** (alert already firing) → nothing happens. This is
  the deduplication: one alert per breach, not one per evaluation cycle
- **Recovered** (was firing, now under threshold) → mark the alert
  resolved

## Delivery now goes through the notification service

`webhook_url` on a rule is still just a URL, but as of this pass it's no
longer POSTed to directly. `HttpNotificationClient`
(`app/notifier.py`) instead calls `services/notification`'s
`POST /notifications` with `channel="webhook", target=webhook_url` —
per the original design's own principle for why notification is a
separate service ("async and failure-prone... should not be mixed into
business logic"). Retries, delivery tracking, and the actual HTTP POST to
`webhook_url` all now live in that one place instead of being duplicated
here. The `Notifier` protocol's shape didn't change, so `executor.py` —
the actual firing/dedup/resolve logic — needed zero changes to switch
implementations; only what `get_notifier()` constructs by default did.

## Graceful degradation, on purpose

A failure in the notification-service call or the incident-service call
does **not** lose the alert — both are wrapped so a failure there is
logged and the alert row still exists with `incident_id: null` or simply
no notification sent. The alert itself, and Prometheus being queried at
all, are the only two things that block on success; everything downstream
of "an alert now exists" degrades independently. `tests/test_api.py` has
explicit tests for exactly these degraded paths
(`test_webhook_failure_does_not_lose_the_alert`,
`test_incident_service_failure_does_not_lose_the_alert`), not just the
happy path.

## What's real vs simulated in this repo's test runs

Same shape as the deployment service: the evaluation pipeline, dedup,
resolve, and API are tested end-to-end (29 tests) against
`FakeMetricsSource`/`FakeNotifier`/`FakeIncidentClient` standing in for
Prometheus, the notification service, and the incident service, with
Celery in its supported eager test mode. The three real adapters
(`PrometheusMetricsSource`, `HttpNotificationClient`, `HttpIncidentClient`)
have their own tests with the underlying `httpx` call mocked, checking
the exact request built and how the response is parsed — real coverage
of *this code*, not of a live Prometheus/notification service/incident
service, none of which were available to test against here.

## Audit trail

`POST /alerts/rules` emits `alert_rule.created`; `POST
/alerts/{id}/acknowledge` emits `alert.acknowledged`. Alert *firing*
itself isn't separately audited — the `Alert` table this service already
keeps (`GET /alerts`) is the record of that; a duplicate audit event
would just be the same data twice. Both audited actions use `actor:
"system"` (this service doesn't read the X-ICOP-User header the gateway
now forwards -- see the root README's Phase 6 notes), and
a failure recording either never breaks the actual rule creation or
acknowledgement — see `test_audit_failure_does_not_break_rule_creation`
and `test_audit_failure_does_not_break_acknowledge` in `tests/test_api.py`.

## Known simplifications

- Real Alembic migrations now — see the auth service's README for the
  verification approach used across all four services with a database.
- One rule per metric+threshold — no "breach for N consecutive
  evaluations before firing" (flapping protection), so a single noisy
  spike fires and immediately resolves. Real systems usually add a
  `for:` duration; that's a reasonable next addition.
- No escalation (unresolved-and-unacknowledged-for-too-long triggering a
  louder channel) — the original design doc lists this, not built here.
- Still only "webhook" as a channel *concept* on a rule (`webhook_url`,
  not a general channel selector) — the notification service itself
  supports email too, but nothing here exposes picking it per rule yet.

## Run standalone

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://icop:icop@localhost:5432/icop
export CELERY_BROKER_URL=amqp://icop:icop@localhost:5672//
export PROMETHEUS_URL=http://localhost:9090
export INCIDENT_SERVICE_URL=http://localhost:8003
export NOTIFICATION_SERVICE_URL=http://localhost:8007
export AUDIT_SERVICE_URL=http://localhost:8008
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# in another shell:
celery -A app.tasks worker --loglevel=info
# and for periodic evaluation, in a third shell:
celery -A app.tasks beat --loglevel=info
```

## Test

```bash
pip install -r requirements.txt
pytest
```
