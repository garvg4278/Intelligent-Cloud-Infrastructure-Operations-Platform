# Audit Service

An immutable event log. Create and read — that's the entire interface.

## Endpoints

| Method | Path                    | Purpose                                                    |
|--------|--------------------------|----------------------------------------------------------------|
| POST   | `/audit/events`           | Record an event                                                |
| GET    | `/audit/events`           | List, filterable by `actor`/`action`/`resource_type`/`source_service` |
| GET    | `/audit/events/{id}`      | One event's full detail                                        |

## "Immutable" is enforced, not just documented

There is no `PUT`, `PATCH`, or `DELETE` route anywhere in this service.
`test_there_is_no_way_to_mutate_or_delete_an_event` in `tests/test_audit.py`
checks this at the HTTP level — it asserts those methods return `405`
against a real created event, and that the event is byte-for-byte
unchanged afterward. That's a stronger guarantee than "we don't happen to
have written an update endpoint": there's no code path that could.

## Event shape

Each event has an `actor` (who — a user email, or `"system"` for
automated actions), an `action` (what — a dotted string like
`deployment.created` or `user.login`), a `resource_type`/`resource_id`
(which thing), a `source_service` (which service is reporting this), and
optional `before_state`/`after_state` (arbitrary JSON — e.g. a role
change's old and new value). No schema is enforced on `action` strings or
on what's inside `before_state`/`after_state` beyond "valid JSON" — this
service records what it's told, it doesn't validate business meaning.

## Who actually calls this

Fifteen real call sites across five services:

| Service        | Action                          | When                                                    |
|----------------|----------------------------------|--------------------------------------------------------------|
| auth           | `user.registered`                | successful `POST /auth/register`                              |
| auth           | `user.login`                     | successful `POST /auth/login` (not failed attempts)            |
| deployment     | `deployment.triggered`           | every `POST /deployments`                                      |
| deployment     | `deployment.succeeded`           | health check passes after deploy                                |
| deployment     | `deployment.failed`              | deploy fails, or rollback itself also fails, or an unexpected error |
| deployment     | `deployment.rolled_back`         | a health-check failure completes an automatic rollback          |
| incident       | `incident.created`               | `POST /incidents`                                               |
| incident       | `incident.status_changed`        | a *valid* `POST /incidents/{id}/transition` (not a rejected one) |
| alert          | `alert_rule.created`             | `POST /alerts/rules`                                            |
| alert          | `alert.acknowledged`             | `POST /alerts/{id}/acknowledge`                                  |
| infrastructure | `environment.provision_triggered`| every `POST /environments`                                       |
| infrastructure | `environment.ready`              | terraform apply + ansible-playbook both succeed                  |
| infrastructure | `environment.provision_failed`   | terraform apply fails, ansible-playbook fails, or an unexpected error |
| infrastructure | `environment.destroy_triggered`  | every `DELETE /environments/{id}`                                 |
| infrastructure | `environment.destroyed`          | terraform destroy succeeds                                        |
| infrastructure | `environment.destroy_failed`     | terraform destroy fails, or an unexpected error                   |

All fifteen use `actor: "system"` except auth's two, which use the real
user's email — auth is the only service in this platform whose routes
actually read the caller's identity to attribute an action to it. The
gateway verifies every request's identity now and forwards it as an
`X-ICOP-User` header (Phase 6, see the root README) — every other
service just doesn't read that header yet, a smaller gap than "nothing
checks who's calling" was. Every call site wraps its audit call so a
failure recording the event never breaks the action being recorded — see
each service's own tests (`test_audit_failure_does_not_break_*`) for
proof, not just the design intent. Deliberately *not* audited: incident
comments (discussion, not a state change), rejected/invalid transitions
(nothing happened, so nothing to record), alert rule evaluation itself
(that's what the `Alert` table already is — auditing it would just
duplicate data that's already queryable).

## Known simplifications

- Same Alembic-verified-against-SQLite-not-Postgres situation as every
  other database-backed service here.
- The nine call sites above are real but not exhaustive — role changes
  (there's no role-update endpoint to audit yet; auth doesn't have one)
  and notification delivery outcomes are the more obvious remaining gaps.
- No retention policy or archival — every event accumulates forever by
  design (that's what "immutable history" means), but nothing here
  manages storage growth over time.

## Run standalone

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://icop:icop@localhost:5432/icop
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
pip install -r requirements.txt
pytest
```

13 tests, including the HTTP-level immutability check above.
