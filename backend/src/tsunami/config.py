"""Application settings via pydantic-settings."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    data_dir: str = ""
    results_dir: str = ""
    bathymetry_cache_dir: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]
    internal_api_url: str = "http://localhost:8000"
    public_api_url: str = ""

    model_config = {"env_prefix": "TSUNAMI_"}

    def model_post_init(self, __context):
        base = Path(__file__).resolve().parent.parent.parent.parent  # backend/
        if not self.data_dir:
            self.data_dir = str(base / "data")
        if not self.results_dir:
            self.results_dir = str(Path(self.data_dir) / "results")
        if not self.bathymetry_cache_dir:
            self.bathymetry_cache_dir = str(Path(self.data_dir) / "bathymetry")
        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{Path(self.data_dir) / 'tsunami.db'}"
        # Ensure directories exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.bathymetry_cache_dir, exist_ok=True)
        if not self.public_api_url:
            self.public_api_url = self.internal_api_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
