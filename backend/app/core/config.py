from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    DATABASE_URL: str
    APP_PORT: int = 8000
    DEBUG: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
