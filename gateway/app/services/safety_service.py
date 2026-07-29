"""Backward-compatible facade over the formal Safety Policy Engine."""

from __future__ import annotations

import re
from dataclasses import dataclass

from gateway.app.safety.contracts import PolicyAction, PolicyOutcome
from gateway.app.safety.engine import (
    PARENT_MARKERS,
    SAFE_INPUT_FALLBACK,
    SUPERVISED_OUTDOOR_PERMISSION,
    SUPERVISION_REMINDER,
    SafetyPolicyEngine,
)


@dataclass(frozen=True)
class SafetyResult:
    """Compatibility result for callers migrating to PolicyOutcome."""

    is_safe: bool
    rule_id: str | None = None
    reason: str | None = None
    suggested_response: str | None = None
    action: PolicyAction = PolicyAction.ALLOW
    phase: str | None = None
    category: str | None = None


class SafetyService:
    """Expose one engine for all safety phases."""

    SUPERVISED_OUTDOOR_PERMISSION = SUPERVISED_OUTDOOR_PERMISSION

    def __init__(self, engine: SafetyPolicyEngine | None = None) -> None:
        self._engine = engine or SafetyPolicyEngine()

    def evaluate_input(
        self,
        text: str,
        permissions: tuple[str, ...] = (),
    ) -> PolicyOutcome:
        return self._engine.evaluate_input(text, permissions=permissions)

    def evaluate_multimodal_input(
        self,
        text: str,
        visual_observations: str,
        permissions: tuple[str, ...] = (),
    ) -> PolicyOutcome:
        """Evaluate a question together with untrusted visual observations."""

        return self._engine.evaluate_multimodal_input(
            text,
            visual_observations,
            permissions=permissions,
        )

    def evaluate_output(
        self,
        text: str,
        permissions: tuple[str, ...] = (),
    ) -> PolicyOutcome:
        return self._engine.evaluate_output(text, permissions=permissions)

    def evaluate_tool(
        self,
        tool_name: str,
        tools: tuple[str, ...],
    ) -> PolicyOutcome:
        return self._engine.evaluate_tool(tool_name, tools)

    def evaluate_permission(
        self,
        permission_name: str,
        permissions: tuple[str, ...],
    ) -> PolicyOutcome:
        return self._engine.evaluate_permission(permission_name, permissions)

    def check_text(
        self,
        text: str,
        permissions: tuple[str, ...] = (),
    ) -> SafetyResult:
        return self._compatibility_result(
            self.evaluate_input(text, permissions),
            fallback=SAFE_INPUT_FALLBACK,
        )

    def check_response(
        self,
        text: str,
        permissions: tuple[str, ...] = (),
    ) -> SafetyResult:
        return self._compatibility_result(self.evaluate_output(text, permissions))

    def get_supervised_outdoor_guidance(
        self,
        text: str,
        permissions: tuple[str, ...],
    ) -> str | None:
        outcome = self.evaluate_input(text, permissions)
        if outcome.action is PolicyAction.TRANSFORM:
            return outcome.text
        return None

    def normalize_outdoor_response(
        self,
        text: str,
        permissions: tuple[str, ...],
    ) -> str:
        """Compatibility helper retained during the incremental migration."""

        if SUPERVISED_OUTDOOR_PERMISSION not in permissions:
            return text
        normalized = re.sub(r"\*\*|__|^#{1,6}\s*", "", text, flags=re.MULTILINE)
        return re.sub(
            r"\b\d{1,3}[\s‑–—−≈]*°",
            "под углом, указанным производителем точилки",
            normalized,
        )

    def apply_required_guardrails(
        self,
        text: str,
        permissions: tuple[str, ...],
    ) -> str:
        """Compatibility helper retained during the incremental migration."""

        if SUPERVISED_OUTDOOR_PERMISSION not in permissions:
            return text
        if re.search(PARENT_MARKERS, text.lower()):
            return text
        return SUPERVISION_REMINDER + text

    @staticmethod
    def _compatibility_result(
        outcome: PolicyOutcome,
        *,
        fallback: str | None = None,
    ) -> SafetyResult:
        decision = outcome.primary_decision
        return SafetyResult(
            is_safe=outcome.action is not PolicyAction.BLOCK,
            rule_id=decision.rule_id,
            reason=decision.reason,
            suggested_response=outcome.safe_response or fallback,
            action=outcome.action,
            phase=decision.phase.value,
            category=decision.category.value,
        )
