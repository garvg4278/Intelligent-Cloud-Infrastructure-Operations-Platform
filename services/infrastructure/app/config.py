from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg2://icop:icop@localhost:5432/icop"
    # SQLAlchemy's own defaults (pool_size=5, max_overflow=10 -> 15 max
    # connections per pod) were never tuned for this platform -- every
    # service used them unchanged. Raised here: still deliberately
    # conservative, not "as high as possible" -- with up to 8 database-
    # backed services each running up to autoscaling.maxReplicas pods
    # (infra/helm/service-chart/values.yaml, default 10), the AGGREGATE
    # connection count across a fully scaled-out platform can still
    # approach a single Postgres instance's max_connections well before
    # any individual pod's own pool is the bottleneck. Raising per-pod
    # pool size fixes single-pod throughput under load; it does not fix
    # that aggregate ceiling -- a connection pooler in front of Postgres
    # (RDS Proxy, or PgBouncer) is the actual next step for that, and
    # isn't built here (see ROADMAP.md).
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    # Recycle connections older than this rather than never (SQLAlchemy's
    # default) -- avoids errors from a connection RDS or a pooler in
    # front of it silently closed for being idle, which "never recycle"
    # only surfaces as a hard-to-reproduce failure under real traffic
    # patterns, not in a quick local test.
    DB_POOL_RECYCLE_SECONDS: int = 1800
    CELERY_BROKER_URL: str = "amqp://icop:icop@localhost:5672//"
    # Paths (inside the worker container) to this repo's terraform/ and
    # ansible/ directories -- mounted read-only in docker-compose.yml,
    # same idea as the deployment service's CHART_PATH pointing at
    # infra/helm/service-chart.
    TERRAFORM_ROOT: str = "/terraform"
    ANSIBLE_ROOT: str = "/ansible"
    # A real `terraform apply` for an EKS cluster commonly takes
    # 15-20 minutes; this default leaves real headroom rather than
    # matching HelmOrchestrator's much shorter default (a single `helm
    # upgrade` is seconds, not minutes).
    TERRAFORM_APPLY_TIMEOUT_SECONDS: int = 1800
    ANSIBLE_RUN_TIMEOUT_SECONDS: int = 900
    AUDIT_SERVICE_URL: str = "http://localhost:8008"


settings = Settings()
