from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://processmind:change-me-local@127.0.0.1:5432/processmind"
    )
    web_origin: str = "http://localhost:5173"
    app_env: str = "local"
    session_hours: int = Field(default=12, ge=1, le=720)
    auth_hash_key: str = "local-only-replace-before-production"
    upload_dir: str = "./.uploads"
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.app_env != "local" and (
            self.auth_hash_key == "local-only-replace-before-production"
            or len(self.auth_hash_key) < 32
        ):
            raise ValueError("AUTH_HASH_KEY must be configured outside local development")
        return self

    @property
    def secure_cookies(self) -> bool:
        return self.app_env != "local"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
