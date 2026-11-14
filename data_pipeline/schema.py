from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Persona = Literal["ai_ml", "fullstack", "data_analyst"]
Money = float | None


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MarketJob(Record):
    job_id: str = Field(min_length=8)
    source: str
    title: str = Field(min_length=1)
    description: str | None = None
    skills: list[str] = Field(default_factory=list)
    skills_source: Literal["tags", "keywords"] | None = None
    category: str | None = None
    budget_type: Literal["fixed", "hourly"] | None = None
    budget_min: Money = Field(default=None, ge=0)
    budget_max: Money = Field(default=None, ge=0)
    hourly_min: Money = Field(default=None, ge=0)
    hourly_max: Money = Field(default=None, ge=0)
    currency: str = "USD"
    client_country: str | None = None
    posted_at: datetime | None = None
    experience_level: str | None = None
    connects_cost: int | None = Field(default=None, ge=0, le=100)
    connects_source: Literal["real", "rule"] | None = None
    persona_tags: list[Persona] = Field(default_factory=list)
    dup_group: str | None = None

    @model_validator(mode="after")
    def check_ranges(self) -> "MarketJob":
        for low, high in ((self.budget_min, self.budget_max), (self.hourly_min, self.hourly_max)):
            if low is not None and high is not None and high < low:
                raise ValueError("range max is below min")
        return self


class ContractRecord(Record):
    contract_id: str = Field(min_length=8)
    title: str = Field(min_length=1)
    contract_type: Literal["fixed", "hourly"]
    status: Literal["ended", "ongoing"]
    start_date: datetime | None = None
    end_date: datetime | None = None
    duration_days: float | None = Field(default=None, ge=0)
    total_hours: float = Field(ge=0)
    total_paid: float = Field(ge=0)
    hourly_rate: Money = Field(default=None, ge=0)
    freelancer_id: str
    persona_tags: list[Persona] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_type(self) -> "ContractRecord":
        if self.contract_type == "hourly" and self.hourly_rate is None:
            raise ValueError("hourly contract needs hourly_rate")
        return self


class ScamExample(Record):
    text: str = Field(min_length=1)
    label: Literal["fake", "real"]
    source: str
    templated: bool = False
