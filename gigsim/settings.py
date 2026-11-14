import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Auth(Strict):
    admin_token_env: str
    admin_token_default: str

    @property
    def admin_token(self) -> str:
        return os.getenv(self.admin_token_env) or self.admin_token_default


class Pagination(Strict):
    default_limit: int = Field(gt=0)
    max_limit: int = Field(gt=0)


class RateLimit(Strict):
    capacity: int = Field(gt=0)
    refill_per_second: float = Field(gt=0)


class Chaos(Strict):
    error_rate: float = Field(ge=0, lt=1)
    latency_ms_max: int = Field(ge=0)


class LLMJudge(Strict):
    model: str
    base_url: str
    api_key_env: str
    weight: float = Field(ge=0, le=1)
    cache_dir: Path


class ClientSim(Strict):
    mode: Literal["rule_only", "blended"]
    view_delay_hours: tuple[int, int]
    final_delay_hours: tuple[int, int]
    followup_delay_hours: tuple[int, int]
    base_view: float = Field(ge=0, le=1)
    injection_share: float = Field(ge=0, lt=1)
    llm: LLMJudge


class Settings(Strict):
    seed: int
    start_time: datetime
    scenario: Literal["live", "dev"]
    storage: Path
    seed_dir: Path
    policies_dir: Path
    policy: str
    auth: Auth
    stream_release_days: int = Field(gt=0)
    screening_share: float = Field(ge=0, le=1)
    pagination: Pagination
    rate_limit: RateLimit
    chaos: Chaos
    clients: ClientSim

    def path(self, value: Path) -> Path:
        return value if value.is_absolute() else ROOT / value


def merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings(path: Path = CONFIG_PATH, overrides: dict[str, Any] | None = None) -> Settings:
    raw = yaml.safe_load(path.read_text())
    return Settings.model_validate(merge(raw, overrides or {}))
