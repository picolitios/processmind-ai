from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://processmind:change-me-local@localhost:5432/processmind"
    web_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
