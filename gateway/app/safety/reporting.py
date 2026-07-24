"""Content-free reports for the protected Safety Admin dashboard."""

from datetime import UTC, datetime

from gateway.app.safety.catalog import RULE_CATALOG
from gateway.app.safety.metrics import safety_metrics_registry
from gateway.app.safety.scenarios import run_scenarios


def policy_snapshot() -> dict[str, object]:
    started_at, metrics = safety_metrics_registry.snapshot()
    counts = {metric.rule_id: metric.count for metric in metrics}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics_started_at": started_at.isoformat(),
        "rules": [
            {
                "rule_id": rule.rule_id,
                "phase": rule.phase.value,
                "category": rule.category.value,
                "action": rule.action.value,
                "title": rule.title,
                "mandatory": rule.mandatory,
                "count": counts.get(rule.rule_id, 0),
            }
            for rule in RULE_CATALOG
        ],
    }


def scenario_report() -> dict[str, object]:
    results = run_scenarios()
    passed = sum(result.passed for result in results)
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": [
            {
                "scenario_id": result.scenario_id,
                "passed": result.passed,
                "expected_action": result.expected_action.value,
                "actual_action": result.actual_action.value,
                "expected_rule_id": result.expected_rule_id,
                "actual_rule_id": result.actual_rule_id,
            }
            for result in results
        ],
    }
