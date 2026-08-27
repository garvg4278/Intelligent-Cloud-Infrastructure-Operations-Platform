# API Gateway

Single entry point for external traffic: correlation IDs, Redis-backed
rate limiting, centralized error handling, and versioned routing under
`/api/v1/*`.

## What it actually does today

- Forwards `/api/v1/auth/*` to the auth service (`AUTH_SERVICE_URL`) and
  `/api/v1/deployments*` to the deployment service (`DEPLOYMENT_SERVICE_URL`)
- Returns `503` if the upstream service is unreachable, rather than
  hanging or leaking a raw connection error
- Adds/echoes `X-Correlation-ID` on every response, including error
  responses (429s, 500s)
- Rate-limits by client IP (fixed window, Redis-backed) -- `/health` and
  `/metrics` are exempt
- Returns a structured `501` for every other documented-but-unbuilt
  service (`monitoring`, `alerts`, `incidents`, `analytics`, `ai`,
  `audit`), naming the phase it's planned for

## What it does not do yet

- No JWT verification at the gateway layer itself -- the auth service
  verifies tokens on its own protected routes. A gateway-level check
  (so downstream services can trust an already-validated identity) is
  worth adding now that there are two real downstream services to
  protect, not just one.
- Rate limiting is per-IP and fixed-window, not per-user or sliding-window.

## Run standalone

```bash
pip install -r requirements.txt
export AUTH_SERVICE_URL=http://localhost:8001
export DEPLOYMENT_SERVICE_URL=http://localhost:8002
export REDIS_URL=redis://localhost:6379/0
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
pip install -r requirements.txt
pytest
```

Tests run against `fakeredis` and a mocked auth-service HTTP client --
no real Redis or running auth service needed.
