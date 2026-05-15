from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")

    REDIS_URL: str = "redis://localhost:6379/0"
    UPLOAD_DIR: str = "/app/data/uploads"
    OUTPUT_DIR: str = "/app/data/outputs"
    WORKER_ID: str = ""


settings = Settings()
