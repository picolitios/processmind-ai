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
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma3:4b"
    ollama_timeout_seconds: int = Field(default=30, ge=1, le=120)
    audit_dispatch_mode: str = "database"
    audit_config_mode: str = "legacy"
    audit_config_write_mode: str = "database"
    audit_internal_url: str = "http://127.0.0.1:8000"
    business_event_write_mode: str = "dual"
    rabbitmq_host: str = "127.0.0.1"
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    business_auth_mode: str = "database"
    identity_internal_url: str = "http://127.0.0.1:8001"

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.audit_dispatch_mode not in {"database", "broker"}:
            raise ValueError("AUDIT_DISPATCH_MODE must be database or broker")
        if self.audit_config_mode not in {"legacy", "owned"}:
            raise ValueError("AUDIT_CONFIG_MODE must be legacy or owned")
        if self.audit_config_write_mode not in {"database", "coordinated"}:
            raise ValueError("AUDIT_CONFIG_WRITE_MODE must be database or coordinated")
        if self.audit_config_write_mode == "coordinated" and self.audit_config_mode != "owned":
            raise ValueError("AUDIT_CONFIG_MODE must be owned for coordinated writes")
        if self.business_event_write_mode not in {"dual", "owned"}:
            raise ValueError("BUSINESS_EVENT_WRITE_MODE must be dual or owned")
        if self.business_auth_mode not in {"database", "identity"}:
            raise ValueError("BUSINESS_AUTH_MODE must be database or identity")
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
