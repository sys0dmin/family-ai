"""Stable contracts shared by policy rules, services and Admin."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PolicyAction(StrEnum):
    ALLOW = "ALLOW"
    TRANSFORM = "TRANSFORM"
    BLOCK = "BLOCK"


class PolicyPhase(StrEnum):
    INPUT = "input"
    OUTPUT = "output"
    TOOL = "tool"
    PERMISSION = "permission"


class PolicyCategory(StrEnum):
    CHILD_SAFETY = "child_safety"
    PRIVACY = "privacy"
    CYBER_SAFETY = "cyber_safety"
    OUTDOOR_SAFETY = "outdoor_safety"
    TOOL_ACCESS = "tool_access"
    PRESENTATION = "presentation"


@dataclass(frozen=True)
class PolicyRuleDescriptor:
    rule_id: str
    phase: PolicyPhase
    category: PolicyCategory
    action: PolicyAction
    title: str
    mandatory: bool = True


@dataclass(frozen=True)
class PolicyDecision:
    rule_id: str
    phase: PolicyPhase
    category: PolicyCategory
    action: PolicyAction
    reason: str


@dataclass(frozen=True)
class PolicyOutcome:
    action: PolicyAction
    text: str
    decisions: tuple[PolicyDecision, ...]
    safe_response: str | None = None

    @property
    def primary_decision(self) -> PolicyDecision:
        return self.decisions[-1]
