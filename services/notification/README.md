# Notification Service

Separated out from the alert service on purpose, per the original design:
"notifications are async and failure-prone. They should not be mixed
into business logic." Two real delivery channels, real retry logic with
backoff, and every attempt tracked.

## Endpoints

| Method | Path                    | Purpose                                        |
|--------|--------------------------|---------------------------------------------------|
| POST   | `/notifications`         | Create + deliver (202, async — see below)          |
| GET    | `/notifications`         | List, filterable by `status_filter`/`channel`        |
| GET    | `/notifications/{id}`    | One notification's current status and error history |

## Two real channels

- **webhook** — needs no configuration, always available: a POST with
  `{"subject", "body"}` to whatever URL you give it.
- **email** — real SMTP via Python's stdlib `smtplib`, STARTTLS on port
  587. Only registered if `SMTP_HOST` is set; without it, a notification
  requesting the `email` channel fails cleanly with "no sender registered
  for channel 'email'" instead of the service refusing to start.

Both implement the same `Sender` protocol, so adding Slack/Teams/SMS
later is a third implementation, not a rewrite of the delivery logic.

## Retry logic

Up to `max_attempts` (default 3, configurable per notification) with
exponential backoff (2s, 4s, 8s..., capped at 30s) between tries, all
within one delivery attempt — not re-queued through Celery for every
retry. Every failed attempt is recorded (`attempts` count, `last_error`);
exhausting all attempts marks the notification `failed` rather than
losing it silently.

**Why not Celery's own `self.retry()`:** this repo relies on Celery's
*eager* mode for testing everywhere it uses Celery, and eager mode's
interaction with `self.retry()`/countdown scheduling is a real subtlety
that would need its own verification to trust blindly. A synchronous
retry loop with **dependency-injected sleep** (`sleep_fn` — swapped for a
no-op in tests) is simpler to reason about, just as real a pattern
(plenty of production code retries exactly this way), and lets the retry
logic itself — not just the eventual delivery — be fully unit tested
without any test actually waiting through backoff. See
`test_sleep_is_called_between_attempts_not_after_the_last_one` in
`tests/test_executor.py`.

## Template rendering

`{{key}}` substitution from a flat `context` dict, applied to both
`subject` and `body` before storage — deliberately minimal (no loops, no
conditionals). An unmatched placeholder is left as-is rather than
raising, so a typo in a template doesn't fail delivery outright.

## Known simplifications

- Same Alembic-verified-against-SQLite-not-Postgres situation as every
  other database-backed service here.
- SMTP always uses STARTTLS on the configured port — covers the common
  case (587, e.g. Gmail/SendGrid SMTP) but not implicit-TLS (465) or
  unencrypted (25) setups.
- **Now actually called:** the alert service delivers firing alerts
  through this service (`services/alert/app/notifier.py`'s
  `HttpNotificationClient`) instead of POSTing to the webhook URL
  directly — the integration this README used to list as "the natural
  next step" is done. Nothing else in the platform calls this service
  yet, but the pattern (one HTTP call to `POST /notifications`, wrapped
  so a failure here doesn't break the caller) is established and the
  same for anything that adds a second caller.

## Run standalone

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://icop:icop@localhost:5432/icop
export CELERY_BROKER_URL=amqp://icop:icop@localhost:5672//
# optional -- omit to leave the "email" channel unregistered
export SMTP_HOST=smtp.example.com
export SMTP_USERNAME=...
export SMTP_PASSWORD=...
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# in another shell:
celery -A app.tasks worker --loglevel=info
```

## Test

```bash
pip install -r requirements.txt
pytest
```

25 tests: 5 templating, 6 retry-logic (the core of this service), 7 API,
7 on the two real senders (mocked `httpx`/`smtplib`).
