"""Configuration schemas."""

from pydantic import BaseModel


class AppConfig(BaseModel):
    environment_name: str
    api_port: int
    database_url: str
    redis_url: str
