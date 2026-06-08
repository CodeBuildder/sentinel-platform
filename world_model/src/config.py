from pydantic_settings import BaseSettings


class Config(BaseSettings):
    SERVICE_NAME: str = "world-model"
    REDIS_URL: str = "redis://localhost:6379"
    FRAGILITY_DEFAULT: float = 0.0
    SLO_WINDOW_DAYS: int = 30
    TRUST_PROMOTE_THRESHOLD: int = 5
    TRUST_BRIER_SURPRISE_THRESHOLD: float = 0.25

    model_config = {"env_prefix": "WM_", "env_file": ".env", "extra": "ignore"}


config = Config()
