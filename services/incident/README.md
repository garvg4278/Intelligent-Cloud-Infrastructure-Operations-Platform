# Incident Service

Tracks incidents through a fixed status lifecycle, with every status
change and comment recorded as an ordered timeline event. Doesn't decide
*when* an incident should exist — that's the alert service's job (or
anyone else's — `POST /incidents` doesn't require an alert, a human can
open one directly).

## Endpoints

| Method | Path                          | Purpose                                    |
|--------|-------------------------------|----------------------------------------------|
| POST   | `/incidents`                  | Open a new incident (starts `open`)           |
| GET    | `/incidents`                  | List, filterable by `status_filter`/`service_name`/`severity` |
| GET    | `/incidents/{id}`              | Detail, including the full timeline           |
| POST   | `/incidents/{id}/transition`  | Move to a new status (validated, see below)   |
| POST   | `/incidents/{id}/comments`    | Add a free-text timeline entry                |
| GET    | `/health`, `/metrics`          | Ops endpoints, same as every other service    |

## Status lifecycle

```
open ──► acknowledged ──► investigating ──► mitigated ──► resolved ──► closed
  │                              │                            ▲   │
  └──────────────────────────────┴────────────────────────────┘   └─► (terminal)
                    (any of these can also jump straight to resolved)   resolved can go back to investigating (reopen)
```

The exact allowed-transitions graph is `ALLOWED_TRANSITIONS` in
`app/models.py` — it's enforced in `crud.transition_status`, not just
documented; an invalid jump (e.g. `open` straight to `mitigated`, or
anything out of `closed`) gets a `409`, not a silent no-op.

## How this connects to the rest of the platform

The alert service calls `POST /incidents` when a new (non-duplicate)
alert fires, with `source_alert_id` set. That's a plain HTTP call, not a
shared database write — `source_alert_id` is stored here as an opaque
string, not a real foreign key, because these are two different
services' data even though they currently share one Postgres instance.
If the alert service is down or the call fails, the alert itself still
gets recorded and notified on — a missing incident link is logged and
degrades gracefully rather than losing the alert. See
`services/alert/app/executor.py`.

## Audit trail

`POST /incidents` emits `incident.created`; a *valid* `POST
/incidents/{id}/transition` emits `incident.status_changed` with both
the before and after status. An invalid transition (409, nothing
actually changed) emits nothing — there's no state change to record.
Comments don't emit anything either — they're discussion, not a state
change. Both audited actions use `actor: "system"` (no caller identity
available here; see the root README's known simplifications), and a
failure recording either never breaks the actual create/transition — see
`test_audit_failure_does_not_break_incident_creation` and
`test_audit_failure_does_not_break_a_transition` in
`tests/test_incidents.py`.

## Known simplifications

- Real Alembic migrations now — see the auth service's README for the
  verification approach used across all four services with a database.
- No postmortem generation — the timeline (`GET /incidents/{id}`) is the
  raw material for one, but nothing assembles it into a document yet.
- No ownership/assignment field — an incident doesn't currently track
  who's working it, only its status and timeline.

## Run standalone

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://icop:icop@localhost:5432/icop
export AUDIT_SERVICE_URL=http://localhost:8008
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
pip install -r requirements.txt
pytest
```
