from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    APP_PORT: int = 8000
    DEBUG: bool = True

    SECRET_KEY: str = "dev-insecure-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    AUTH_ADMIN_USERNAME: str | None = None
    AUTH_ADMIN_PASSWORD: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
