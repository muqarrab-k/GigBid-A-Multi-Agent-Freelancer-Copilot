import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, get_args

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).with_name("config.yaml")

NodeName = Literal[
    "scout",
    "analyst",
    "risk_assessor",
    "fit_matcher",
    "pricing",
    "writer",
    "verifier",
    "critic",
    "compliance",
    "client_liaison",
]
NODE_NAMES: tuple[str, ...] = get_args(NodeName)


class ConfigError(RuntimeError):
    """Bad or missing config."""


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelSpec(Strict):
    provider: str
    model: str
    base_url: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class NodeModel(ModelSpec):
    fallback: ModelSpec | None = None


class Profile(Strict):
    scout: NodeModel
    analyst: NodeModel
    risk_assessor: NodeModel
    fit_matcher: NodeModel
    pricing: NodeModel
    writer: NodeModel
    verifier: NodeModel
    critic: NodeModel
    compliance: NodeModel
    client_liaison: NodeModel

    def node(self, name: str) -> NodeModel:
        if name not in NODE_NAMES:
            raise ConfigError(f"unknown node '{name}', expected one of {NODE_NAMES}")
        spec: NodeModel = getattr(self, name)
        return spec

    def specs(self) -> list[ModelSpec]:
        out: list[ModelSpec] = []
        for name in NODE_NAMES:
            spec = self.node(name)
            out.append(spec)
            if spec.fallback:
                out.append(spec.fallback)
        return out


class Provider(Strict):
    api_key_env: str | None = None
    base_url_env: str | None = None


class GeneratorSpec(ModelSpec):
    max_tokens: int = Field(default=2000, gt=0)
    reasoning_effort: Literal["none", "low", "medium", "high"] | None = None
    usd_per_mtok_in: float = Field(ge=0)
    usd_per_mtok_out: float = Field(ge=0)


class ModelsConfig(Strict):
    active_profile: str = "open"
    request_timeout_s: float = Field(default=60, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    providers: dict[str, Provider]
    active_generator: str = "default"
    generators: dict[str, GeneratorSpec] = Field(default_factory=dict)
    profiles: dict[str, Profile]

    @property
    def generator(self) -> GeneratorSpec:
        if self.active_generator not in self.generators:
            raise ConfigError(f"generator '{self.active_generator}' not in {sorted(self.generators)}")
        return self.generators[self.active_generator]

    @model_validator(mode="after")
    def check_profiles(self) -> "ModelsConfig":
        if "open" not in self.profiles:
            raise ValueError("the 'open' profile is required")
        if self.active_profile not in self.profiles:
            raise ValueError(
                f"active profile '{self.active_profile}' not in {sorted(self.profiles)}"
            )
        for name, profile in self.profiles.items():
            for spec in profile.specs():
                if spec.provider not in self.providers:
                    raise ValueError(f"profile '{name}' uses unknown provider '{spec.provider}'")
        for name, gen in self.generators.items():
            if gen.provider not in self.providers:
                raise ValueError(f"generator '{name}' uses unknown provider '{gen.provider}'")
        return self


class RateLimit(Strict):
    requests_per_minute: int = Field(gt=0)
    burst: int = Field(default=5, gt=0)
    poll_interval_minutes: int = Field(gt=0)


class RateLimits(Strict):
    gigsim: RateLimit
    upwork: RateLimit


class MarketplaceConfig(Strict):
    mode: Literal["gigsim", "upwork"] = "gigsim"
    gigsim_base_url_env: str = "GIGSIM_BASE_URL"
    gigsim_base_url_default: str = "http://localhost:8081"
    upwork_mcp_url: str
    timeout_s: float = Field(default=15, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    backoff_s: float = Field(default=0.5, ge=0)
    backoff_max_s: float = Field(default=8, ge=0)
    rate_limits: RateLimits

    @property
    def gigsim_base_url(self) -> str:
        return os.getenv(self.gigsim_base_url_env) or self.gigsim_base_url_default

    @property
    def rate_limit(self) -> RateLimit:
        limit: RateLimit = getattr(self.rate_limits, self.mode)
        return limit


class Targets(Strict):
    p95_latency_s_per_job: float = Field(gt=0)
    p95_latency_s_per_proposal: float = Field(gt=0)
    cost_usd_per_job: float = Field(ge=0)
    cost_usd_per_proposal: float = Field(ge=0)


class Budgets(Strict):
    max_graph_steps: int = Field(gt=0)
    max_revisions: int = Field(ge=0, le=5)
    max_tokens_per_job: int = Field(gt=0)
    targets: Targets


class Thresholds(Strict):
    minimum_fit_score: float = Field(ge=0, le=1)
    watch_fit_score: float = Field(ge=0, le=1)
    maximum_risk_score: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def check_order(self) -> "Thresholds":
        if self.watch_fit_score > self.minimum_fit_score:
            raise ValueError("watch_fit_score must not exceed minimum_fit_score")
        return self


class ConnectsTier(Strict):
    max_budget: float | None = Field(default=None, gt=0)
    connects: int = Field(gt=0)


class ConnectsRule(Strict):
    hourly_default: int = Field(gt=0)
    unknown_default: int = Field(gt=0)
    fixed_tiers: list[ConnectsTier] = Field(min_length=1)

    @model_validator(mode="after")
    def check_tiers(self) -> "ConnectsRule":
        if self.fixed_tiers[-1].max_budget is not None:
            raise ValueError("last connects tier needs max_budget: null")
        caps = [t.max_budget for t in self.fixed_tiers[:-1] if t.max_budget is not None]
        if len(caps) != len(self.fixed_tiers) - 1 or caps != sorted(caps):
            raise ValueError("connects tiers must be sorted by max_budget")
        return self

    def connects_for(self, budget_type: str | None, budget: float | None) -> int:
        if budget_type == "hourly":
            return self.hourly_default
        if budget is None:
            return self.unknown_default
        for tier in self.fixed_tiers:
            if tier.max_budget is None or budget <= tier.max_budget:
                return tier.connects
        return self.unknown_default


class BiddingRules(Strict):
    currency: str = "USD"
    weekly_connects_budget: int = Field(ge=0)
    max_connects_per_job: int = Field(gt=0)
    connects_unit_cost_usd: float = Field(ge=0)
    min_hourly_rate: float = Field(ge=0)
    min_fixed_price: float = Field(ge=0)
    platform_fee_pct: float = Field(ge=0, lt=100)
    max_proposals_per_day: int = Field(gt=0)
    connects_rule: ConnectsRule
    extra: dict[str, Any] = Field(default_factory=dict)


class Paths(Strict):
    policy_pack: Path
    prompts_dir: Path
    personas_dir: Path
    processed_dir: Path
    raw_dir: Path
    seed_dir: Path

    @field_validator("*")
    @classmethod
    def from_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else ROOT / value


class SplitSizes(Strict):
    history: int = Field(gt=0)
    stream: int = Field(gt=0)
    dev_pool: int = Field(gt=0)


class DataConfig(Strict):
    seed: int
    split_sizes: SplitSizes
    off_topic_share: float = Field(ge=0, lt=1)
    stream_dup_cap: int = Field(default=1, ge=1)
    min_description_words: int = Field(default=20, ge=0)
    pricing_min_count: int = Field(default=30, gt=0)
    max_fixed_budget: float = Field(gt=0)
    max_hourly_rate: float = Field(gt=0)
    contract_date_min: date
    contract_date_max: date


class SynthConfig(Strict):
    proposals_per_persona: int = Field(gt=0)
    reviews_per_persona: int = Field(gt=0)
    label_noise: float = Field(ge=0, lt=0.5)
    clients: int = Field(gt=0)
    scammer_share: float = Field(ge=0, lt=1)
    scam_share: float = Field(ge=0, lt=1)
    injection_share: float = Field(ge=0, lt=1)
    holdout_size: int = Field(ge=0)
    dev_jobs_per_persona: int = Field(gt=0)
    relevant_evidence_k: int = Field(gt=0)
    bid_min_skill_hits: int = Field(ge=1)
    bid_min_coverage: float = Field(ge=0, le=1)


class McpUser(Strict):
    user: str
    tenant: str
    timezone: str
    token_env: str
    token_default: str
    gigsim_token_env: str
    gigsim_token_default: str

    @property
    def token(self) -> str:
        return os.getenv(self.token_env) or self.token_default

    @property
    def gigsim_token(self) -> str:
        return os.getenv(self.gigsim_token_env) or self.gigsim_token_default


class McpLimits(Strict):
    search_limit_max: int = Field(gt=0)
    cover_letter_max_chars: int = Field(gt=0)
    screening_answer_max_chars: int = Field(gt=0)
    max_screening_answers: int = Field(ge=0)
    message_max_chars: int = Field(gt=0)
    bid_max_usd: float = Field(gt=0)
    idempotency_key_max_chars: int = Field(gt=0)
    free_slots_max_days: int = Field(gt=0)
    slot_min_minutes: int = Field(gt=0)
    slot_max_minutes: int = Field(gt=0)
    email_subject_max_chars: int = Field(gt=0)
    email_body_max_chars: int = Field(gt=0)


class WorkspaceMock(Strict):
    seed: int
    work_start_hour: int = Field(ge=0, le=23)
    work_end_hour: int = Field(ge=1, le=24)
    busy_blocks_per_day: int = Field(ge=0)


class McpConfig(Strict):
    audit_dir: Path
    workspace_dir: Path
    default_user: str
    issuer_url: str
    ports: dict[str, int]
    limits: McpLimits
    workspace: WorkspaceMock
    users: list[McpUser] = Field(min_length=1)

    @field_validator("audit_dir", "workspace_dir")
    @classmethod
    def from_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else ROOT / value

    @model_validator(mode="after")
    def check_users(self) -> "McpConfig":
        names = [u.user for u in self.users]
        if len(set(names)) != len(names):
            raise ValueError("duplicate mcp users")
        if self.default_user not in names:
            raise ValueError(f"default_user '{self.default_user}' not in mcp.users")
        return self

    def user(self, name: str) -> McpUser:
        return next(u for u in self.users if u.user == name)


class EmbedderSpec(Strict):
    provider: Literal["sentence_transformers", "ollama", "fake"]
    model: str
    dim: int = Field(gt=0)
    batch_size: int = Field(default=32, gt=0)
    trust_remote_code: bool = False
    query_prefix: str = ""
    document_prefix: str = ""
    base_url: str | None = None


class EmbeddingsConfig(EmbedderSpec):
    fallback: EmbedderSpec | None = None
    ollama: EmbedderSpec | None = None
    cache_path: Path

    @field_validator("cache_path")
    @classmethod
    def from_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else ROOT / value


class ChunkingConfig(Strict):
    strategy: Literal["fixed"] = "fixed"
    size_words: int = Field(gt=10)
    overlap_words: int = Field(ge=0)

    @model_validator(mode="after")
    def check_overlap(self) -> "ChunkingConfig":
        if self.overlap_words >= self.size_words:
            raise ValueError("overlap_words must be smaller than size_words")
        return self


class StoreConfig(Strict):
    backend: Literal["pgvector", "memory"] = "pgvector"
    dsn_env: str = "DATABASE_URL"
    dsn_default: str
    schema_name: str = Field(default="rag", alias="schema", pattern=r"^[a-z_]+$")

    @property
    def dsn(self) -> str:
        # psycopg wants plain postgresql://
        return (os.getenv(self.dsn_env) or self.dsn_default).replace("postgresql+psycopg://", "postgresql://")


class RerankerSpec(Strict):
    provider: str
    model: str


class RagConfig(Strict):
    variant: str = "v0"
    default_k: int = Field(default=5, gt=0)
    candidate_multiplier: int = Field(default=6, gt=0)
    embeddings: EmbeddingsConfig
    chunking: ChunkingConfig
    store: StoreConfig
    reranker: RerankerSpec


class Settings(Strict):
    models: ModelsConfig
    marketplace: MarketplaceConfig
    budgets: Budgets
    thresholds: Thresholds
    bidding_rules: BiddingRules
    paths: Paths
    data: DataConfig
    synth: SynthConfig
    mcp: McpConfig
    rag: RagConfig

    @property
    def profile(self) -> Profile:
        return self.models.profiles[self.models.active_profile]


class EnvOverrides(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    model_profile: str | None = None
    marketplace_mode: str | None = None


def load_config(path: Path = CONFIG_PATH) -> Settings:
    """Read YAML, apply env overrides, validate."""
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as err:
        raise ConfigError(f"cannot read config {path}: {err}") from err
    if not isinstance(raw, dict):
        raise ConfigError(f"config {path} must be a mapping")

    # env overrides
    env = EnvOverrides()
    if env.model_profile:
        raw.setdefault("models", {})["active_profile"] = env.model_profile
    if env.marketplace_mode:
        raw.setdefault("marketplace", {})["mode"] = env.marketplace_mode

    try:
        return Settings.model_validate(raw)
    except ValidationError as err:
        raise ConfigError(f"invalid config {path}:\n{err}") from err


@lru_cache(maxsize=1)
def get_config() -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    return load_config()
