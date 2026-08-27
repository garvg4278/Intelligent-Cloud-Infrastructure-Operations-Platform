# Auth Service

Users, JWT (access + refresh), and RBAC. Nothing else.

## Endpoints

| Method | Path            | Auth           | Purpose                        |
|--------|-----------------|----------------|---------------------------------|
| POST   | `/auth/register`| none           | Create a user (always `viewer`) |
| POST   | `/auth/login`   | none           | OAuth2 password flow -> tokens  |
| POST   | `/auth/refresh` | refresh token  | Rotate access + refresh tokens  |
| GET    | `/auth/me`      | access token   | Current user                    |
| GET    | `/auth/users`   | admin only     | List all users                  |
| GET    | `/health`       | none           | Liveness                        |
| GET    | `/metrics`      | none           | Prometheus exposition format    |

## Schema migrations

Real Alembic migrations, not `create_all()` — `alembic/env.py` reads
`DATABASE_URL` from this service's own `Settings` (one source of truth,
not duplicated in `alembic.ini`). The initial migration
(`alembic/versions/*_initial_schema.py`) was generated with
`--autogenerate` and verified against a real SQLite DB: the resulting
schema matches `Base.metadata.create_all()` exactly, the app functions
normally against a migrated DB, `alembic downgrade base` cleanly drops
everything, and re-running `upgrade head` is a correct no-op. Not
verified against real Postgres specifically (no live Postgres was
available while building this) — but every column type here
(`String(36)` ids, `native_enum=False` enums, `DateTime(timezone=True)`)
was already chosen to be portable across SQLite and Postgres, so this is
lower-risk than it might otherwise be.

## Audit trail

`POST /auth/register` and successful `POST /auth/login` each emit an
audit event (`user.registered`, `user.login`) to the audit service, with
the real user's email as the actor — this is the only service in the
platform with an actual identity to attribute an action to. Failed login
attempts do not emit one. A failure recording the event never breaks
registration or login itself (`AuditClientError` is caught and logged,
not propagated) — see `test_audit_service_failure_does_not_break_*` in
`tests/test_auth.py`.

## Run standalone

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://icop:icop@localhost:5432/icop
export AUDIT_SERVICE_URL=http://localhost:8008
alembic upgrade head
uvicorn app.main:app --reload
```

## Test

```bash
pip install -r requirements.txt
pytest
```

Tests run against an in-memory SQLite database built via
`Base.metadata.create_all()` directly, not through Alembic and not
against the configured `DATABASE_URL` — that's a deliberate speed choice
for the test suite, not an inconsistency; production schema changes go
through migrations, fast in-memory tests don't need to.
