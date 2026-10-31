from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "dev-secret-change-me"
MIN_SECRET_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "local" (docker-compose, tests) tolerates the dev secret; anything else
    # -- including the unset default -- refuses to start with it. Secure by
    # default: a real deployment that forgets to set SECRET_KEY crashes at
    # boot instead of silently accepting tokens anyone can forge.
    ICOP_ENV: str = "production"

    # Same default as services/auth/app/config.py on purpose -- both must
    # agree on this value (real deployments set the same SECRET_KEY env
    # var for both, see docker-compose.yml) for the gateway's local JWT
    # verification (see app/security.py) to accept tokens auth actually
    # issued.
    SECRET_KEY: str = INSECURE_DEFAULT_SECRET
    AUTH_SERVICE_URL: str = "http://localhost:8001"
    DEPLOYMENT_SERVICE_URL: str = "http://localhost:8002"
    INCIDENT_SERVICE_URL: str = "http://localhost:8003"
    ALERT_SERVICE_URL: str = "http://localhost:8004"
    AIOPS_SERVICE_URL: str = "http://localhost:8005"
    ANALYTICS_SERVICE_URL: str = "http://localhost:8006"
    NOTIFICATION_SERVICE_URL: str = "http://localhost:8007"
    AUDIT_SERVICE_URL: str = "http://localhost:8008"
    INFRASTRUCTURE_SERVICE_URL: str = "http://localhost:8009"
    REDIS_URL: str = "redis://localhost:6379/0"
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    # See app/middleware/rate_limit.py's _client_ip for why this defaults
    # False and exactly when it's safe to flip -- short version: only once
    # a real load balancer/ingress actually sits in front of this gateway,
    # which isn't built yet (see gitops/bootstrap/argocd-values.yaml).
    TRUST_PROXY_HEADERS: bool = False
    # Real gap this closes: neither FastAPI nor uvicorn enforce any
    # request body size limit by default, and this gateway read the
    # entire body into memory (`await request.body()`) before forwarding
    # it, for every route, regardless of size. A flood of large request
    # bodies was a real, if unglamorous, memory-exhaustion vector against
    # the one process every single request already passes through. 10 MB
    # is deliberately generous for what this platform's real payloads
    # look like (the largest legitimate body is probably a
    # deployment/alert/incident JSON blob or an infrastructure
    # provisioning request, nowhere near this) while still bounding the
    # worst case to something a single pod can absorb repeatedly.
    MAX_REQUEST_BODY_BYTES: int = 10 * 1024 * 1024
    # Comma-separated allow-list, e.g. "https://app.example.com,http://localhost:5173".
    # Empty by default -- no frontend exists in this repo yet (see the
    # root README), so the honest default is "no cross-origin access at
    # all" rather than guessing at a dev URL nothing actually uses today.
    # Deliberately never a wildcard: CORSMiddleware (see app/main.py)
    # is configured with allow_credentials=True (the gateway forwards a
    # real bearer token, not cookies, but treat it the same way) --
    # combining that with allow_origins=["*"] is a well-known
    # misconfiguration browsers themselves refuse to honor for good
    # reason, so this setting only ever produces an explicit list.
    CORS_ALLOWED_ORIGINS: str = ""
    UPSTREAM_TIMEOUT_SECONDS: float = 10.0
    AI_UPSTREAM_TIMEOUT_SECONDS: float = 180.0

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
