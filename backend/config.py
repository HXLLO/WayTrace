from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    max_concurrent_scrapes: int = 30
    job_ttl_seconds: int = 7200
    max_active_jobs: int = 10
    archive_request_timeout: int = 30
    archive_retry_count: int = 3
    scan_timeout_seconds: int = 3600
    scrape_delay_min: float = 0.02
    scrape_delay_max: float = 0.08
    scrape_max_retries: int = 3
    log_level: str = "INFO"

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @field_validator("max_concurrent_scrapes")
    @classmethod
    def _scrapes_bounds(cls, v: int) -> int:
        if v < 1 or v > 50:
            raise ValueError("max_concurrent_scrapes must be between 1 and 50")
        return v

    @field_validator("max_active_jobs")
    @classmethod
    def _jobs_bounds(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_active_jobs must be >= 1")
        return v

    @field_validator("archive_request_timeout")
    @classmethod
    def _timeout_bounds(cls, v: int) -> int:
        if v < 5 or v > 120:
            raise ValueError("archive_request_timeout must be between 5 and 120")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
