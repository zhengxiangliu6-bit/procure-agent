from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class Requirement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str = Field(default='DEMO-MCU-A', min_length=1, max_length=100)
    quantity: int = Field(default=500, ge=1, le=1000000)
    max_lead_days: int = Field(default=14, ge=1, le=365)
    currency: Literal['CNY'] = 'CNY'
    min_temp: int = -40
    max_temp: int = 85
    package: str = 'LQFP-48'

    @model_validator(mode='after')
    def temperature_order(self):
        if self.min_temp > self.max_temp:
            raise ValueError('最低温度不可高于最高温度')
        return self

class Quote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=100)
    supplier: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(ge=0, max_digits=16, decimal_places=6)
    price_unit: int = Field(default=1, ge=1, le=1000000)
    moq: int = Field(default=1, ge=1, le=1000000)
    lead_days: int | None = Field(default=None, ge=0, le=365)
    tax_included: bool = True
    tax_rate: Decimal | None = Field(default=None, ge=0, le=1)
    shipping: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=6)
    currency: Literal['CNY'] = 'CNY'
    source: str = Field(default='人工录入', max_length=500)

class CreateTask(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(default='元器件采购核验', min_length=1, max_length=100)
    requirement: Requirement = Field(default_factory=Requirement)
    quotes: list[Quote] = Field(min_length=1, max_length=20)

class ResumeTask(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_checkpoint: str
    patches: dict[str, dict] = Field(default_factory=dict)
    approved: bool | None = None
    note: str = Field(default='', max_length=1000)
    answers: dict = Field(default_factory=dict)

class SourcingTask(BaseModel):
    model_config = ConfigDict(extra='forbid')
    goal: str = Field(min_length=5, max_length=1500)
    scenario: Literal['balanced','stockout','budget','impossible'] = 'balanced'

class SourcingGoal(BaseModel):
    """Only explicitly supplied constraints. Missing fields must be clarified."""
    model_config = ConfigDict(extra='forbid')
    model: str | None = None
    quantity: int | None = Field(default=None, ge=1, le=1000000)
    budget: Decimal | None = Field(default=None, gt=0, max_digits=16, decimal_places=2)
    max_lead_days: int | None = Field(default=None, ge=1, le=365)
    package: str | None = None
    min_temp: int | None = None
    max_temp: int | None = None

