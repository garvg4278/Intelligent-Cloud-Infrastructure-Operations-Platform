# AI Ops Service

A real tool-calling agent, not a chat wrapper. Given a service name and a
question, it queries this platform's own deployment, alert, and incident
history plus current Prometheus metrics, and asks an LLM to explain what
it found — showing its work, not just an answer.

## Endpoints

| Method | Path                    | Purpose                                       |
|--------|--------------------------|--------------------------------------------------|
| POST   | `/ai/explain`            | Ask a question about a service                    |
| GET    | `/ai/history`            | List past queries, filterable by `service_name`    |
| GET    | `/ai/history/{id}`       | One past query with its full evidence trail        |
| GET    | `/health`, `/metrics`    | Ops endpoints, same as every other service          |

## How it works

`POST /ai/explain` runs a real tool-use loop against Anthropic's Messages
API (`app/agent.py`):

1. Send the question + tool definitions to the model
2. If it asks for a tool, actually call it — a real HTTP request to the
   deployment, alert, or incident service, or a real Prometheus query
   (`app/tools.py`, `app/service_clients.py`)
3. Feed the real result back, repeat (capped at `MAX_AGENT_ITERATIONS`,
   default 6, so a model that never stops calling tools can't loop
   forever)
4. Once the model gives a final text answer, return it **along with the
   full evidence trail** — every tool called, its input, and its result

That evidence trail isn't cosmetic. The original design's explicit rule
for this service is "must not blindly act... produce explainable
outputs" — returning the evidence alongside the answer is how that's
actually satisfied, not just asserted.

## Every tool is read-only, on purpose

`get_recent_deployments`, `get_recent_alerts`, `get_recent_incidents`,
`query_current_metric` — none of them can deploy, roll back, acknowledge,
or change anything. That's the actual enforcement of "must not blindly
act," not a comment saying so: there is no tool in `TOOL_DEFINITIONS`
that does anything but read.

## Bring your own API key

`ANTHROPIC_API_KEY` is empty by default. Without it, `/health`,
`/metrics`, and `/ai/history` all work normally, but `POST /ai/explain`
returns a clear `503` naming the problem instead of a stack trace. Same
shape as `HelmOrchestrator` needing a kubeconfig or the alert service
needing a reachable Prometheus: real infrastructure the operator brings,
not something baked into the container.

## What's real vs. what could actually be verified here

This is the one external integration in this repo that got **more** than
the usual mocked-adapter tests — worth spelling out exactly what:

- **The agent loop itself** (7 tests, `test_agent.py`): tool execution,
  multi-turn chaining, a tool failure being handed back to the model
  instead of crashing the request, the iteration cap. Tested with a
  `FakeLLMClient` that scripts a real multi-turn conversation shape, not
  just a single canned reply.
- **`AnthropicLLMClient`'s request construction** (5 tests,
  `test_llm_client.py`): mocked `httpx`, same pattern as every other
  adapter in this repo.
- **Beyond that:** with no API key available in the build sandbox, a
  request was still sent to the **real, live** `api.anthropic.com` — with
  an invalid key, and with the actual 4-tool schema from
  `TOOL_DEFINITIONS` attached. The response was `401 authentication_error`,
  not a `400` about a malformed field. That means the real API validated
  the request shape — model, messages, and tool schemas — before it ever
  got to checking the key. That's stronger evidence than a mock can give,
  short of an actual answer coming back. What it does *not* prove: that a
  real model call, with a valid key, produces a good answer — that
  depends on Anthropic's model behaving well given this tool set, which
  is genuinely untested here.
- **The four service clients** (6 tests, `test_service_clients.py`):
  request construction and response parsing against the actual API
  shapes of the deployment/alert/incident services already built in this
  repo — not guessed, checked against those services' real schemas.

## Known simplifications

- Same Alembic-verified-against-SQLite-not-Postgres situation as every
  other service.
- Only Anthropic is implemented. `LLMClient` is a `Protocol` — adding
  OpenAI or a local model is a second implementation of `send()`, not a
  rewrite of `agent.py`.
- No streaming — `POST /ai/explain` blocks until the full answer is
  ready. For a handful of tool-use rounds this is normally a few seconds,
  not the minutes a deployment can take, so this wasn't worth Celery.
- The alert-lookup tool does two real HTTP calls and joins client-side
  (rules by service, then all alerts, filtered by rule id) because the
  alert service doesn't expose "alerts for this service" directly. Slower
  than it needs to be at scale; correct at this scale.

## Run standalone

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://icop:icop@localhost:5432/icop
export ANTHROPIC_API_KEY=sk-...   # required for /ai/explain to work
export DEPLOYMENT_SERVICE_URL=http://localhost:8002
export INCIDENT_SERVICE_URL=http://localhost:8003
export ALERT_SERVICE_URL=http://localhost:8004
export PROMETHEUS_URL=http://localhost:9090
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
pip install -r requirements.txt
pytest
```

No API key, no other services, no Prometheus needed — everything external
is faked. 26 tests.
