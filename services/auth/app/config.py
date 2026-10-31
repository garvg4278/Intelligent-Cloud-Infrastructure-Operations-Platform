from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "dev-secret-change-me"
MIN_SECRET_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # See services/gateway/app/config.py -- same rule, same reason: both
    # services must agree on SECRET_KEY, and both refuse a weak one outside
    # ICOP_ENV=local.
    ICOP_ENV: str = "production"
    SECRET_KEY: str = INSECURE_DEFAULT_SECRET

    # Self-registration always yields a `viewer`, and no endpoint could ever
    # create the first admin -- so without a way in, every privileged action
    # (provisioning, role changes) was unreachable. If both are set, auth
    # creates this admin at startup when no such user exists. Never promotes
    # an existing account, and /auth/register refuses this email, so the
    # address cannot be squatted before the first boot.
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUDIT_SERVICE_URL: str = "http://localhost:8008"

    @model_validator(mode="after")
    def _reject_weak_secret_outside_local(self):
        if self.ICOP_ENV != "local" and (
            self.SECRET_KEY == INSECURE_DEFAULT_SECRET or len(self.SECRET_KEY.encode()) < MIN_SECRET_BYTES
        ):
            raise ValueError(
                "SECRET_KEY must be set to a random value of at least 32 bytes "
                "(e.g. `openssl rand -hex 32`); the built-in dev default is only "
                "accepted when ICOP_ENV=local"
            )
        return self


settings = Settings()
