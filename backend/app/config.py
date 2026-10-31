"""The only configuration boundary of the backend.

`Settings` reads provider keys and switches from `backend/.env`.
`AppConfig` holds fixed policy values that belong in code, not in the environment.
"""

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    llm_provider: Literal["gemini", "nvidia"] = "gemini"

    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None

    nvidia_api_key: SecretStr | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str | None = None

    second_reading: Literal["always", "on_doubt", "never"] = "on_doubt"

    app_access_password: SecretStr | None = None
    app_session_secret: SecretStr | None = None
    allowed_origin: str = "http://localhost:5173"

    @model_validator(mode="after")
    def _require_selected_provider(self) -> Self:
        if self.llm_provider == "gemini":
            missing = [
                name
                for name, value in (
                    ("GEMINI_API_KEY", self.gemini_api_key),
                    ("GEMINI_MODEL", self.gemini_model),
                )
                if not value
            ]
        else:
            missing = [
                name
                for name, value in (
                    ("NVIDIA_API_KEY", self.nvidia_api_key),
                    ("NVIDIA_MODEL", self.nvidia_model),
                )
                if not value
            ]
        if missing:
            raise ValueError(
                f"LLM_PROVIDER={self.llm_provider} needs {', '.join(missing)} in backend/.env "
                "(see backend/.env.example)."
            )
        if self.app_access_password and not self.app_session_secret:
            raise ValueError("APP_ACCESS_PASSWORD is set, so APP_SESSION_SECRET is required too.")
        return self

    @property
    def active_model(self) -> str:
        model = self.gemini_model if self.llm_provider == "gemini" else self.nvidia_model
        assert model is not None
        return model

    @property
    def auth_enabled(self) -> bool:
        return self.app_access_password is not None


@dataclass(frozen=True)
class AppConfig:
    max_upload_bytes: int = 5 * 1024 * 1024
    max_pages: int = 5
    money_tolerance: Decimal = Decimal("1.00")
    confidence_threshold: float = 0.80
    data_dir: Path = BACKEND_DIR / "data"
    samples_dir: Path = REPO_DIR / "samples"


APP_CONFIG = AppConfig()


@lru_cache
def get_settings() -> Settings:
    return Settings()
