from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DEPLOYMENT_SERVICE_URL: str = "http://localhost:8002"
    INCIDENT_SERVICE_URL: str = "http://localhost:8003"
    ALERT_SERVICE_URL: str = "http://localhost:8004"
    REDIS_URL: str = "redis://localhost:6379/0"


settings = Settings()
