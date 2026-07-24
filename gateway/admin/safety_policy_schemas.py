"""Content-free Admin schemas for the formal Safety Policy Engine."""

from datetime import datetime

from pydantic import BaseModel, Field


class SafetyRuleView(BaseModel):
    rule_id: str
    phase: str
    category: str
    action: str
    title: str
    mandatory: bool
    count: int = Field(ge=0)


class SafetyPolicySnapshot(BaseModel):
    generated_at: datetime
    metrics_started_at: datetime
    rules: list[SafetyRuleView]


class SafetyScenarioResult(BaseModel):
    scenario_id: str
    passed: bool
    expected_action: str
    actual_action: str
    expected_rule_id: str
    actual_rule_id: str


class SafetyScenarioReport(BaseModel):
    total: int
    passed: int
    failed: int
    results: list[SafetyScenarioResult]
