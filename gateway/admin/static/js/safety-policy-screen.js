import { api } from "./api-client.js?v=admin-modules-2";
import { byId, formatDateTime, setStatus } from "./dom.js?v=admin-modules-2";

export function createSafetyPolicyScreen({ openAgents }) {
  function render(data) {
    const rules = data.rules || [];
    const countByAction = action => rules
      .filter(rule => rule.action === action)
      .reduce((total, rule) => total + rule.count, 0);
    byId("safety-rule-count").textContent = rules.length;
    byId("safety-decision-count").textContent = rules.reduce(
      (total, rule) => total + rule.count,
      0
    );
    byId("safety-block-count").textContent = countByAction("BLOCK");
    byId("safety-transform-count").textContent = countByAction("TRANSFORM");
    byId("safety-metrics-started").textContent =
      `Счётчики с ${formatDateTime(data.metrics_started_at)}`;
    const body = byId("safety-rule-list");
    body.replaceChildren();
    for (const rule of rules) {
      const row = document.createElement("tr");
      const identity = document.createElement("td");
      const title = document.createElement("strong");
      title.textContent = rule.title;
      const id = document.createElement("div");
      id.className = "rule-id muted";
      id.textContent = rule.rule_id;
      identity.append(title, id);
      const phase = document.createElement("td");
      phase.textContent = rule.phase;
      const category = document.createElement("td");
      category.textContent = rule.category;
      const actionCell = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = `policy-badge ${rule.action.toLowerCase()}`;
      badge.textContent = rule.action;
      actionCell.appendChild(badge);
      const count = document.createElement("td");
      count.textContent = rule.count;
      row.append(identity, phase, category, actionCell, count);
      body.appendChild(row);
    }
  }

  async function load() {
    const status = byId("safety-policy-status");
    try {
      render(await api("/api/safety-policy", { method: "GET" }));
      setStatus(status, "Policy Engine доступен", "ok");
    } catch (error) {
      setStatus(status, `Ошибка: ${error.message}`, "err");
    }
  }

  async function runScenarios() {
    const status = byId("safety-policy-status");
    const button = byId("safety-run-scenarios");
    button.disabled = true;
    try {
      const report = await api("/api/safety-policy/scenarios", {
        method: "POST"
      });
      byId("safety-scenario-state").textContent =
        `${report.passed} / ${report.total}`;
      const list = byId("safety-scenario-list");
      list.replaceChildren();
      for (const result of report.results) {
        const row = document.createElement("div");
        row.className = `scenario-row${result.passed ? "" : " failed"}`;
        const name = document.createElement("strong");
        name.textContent = result.scenario_id;
        const state = document.createElement("span");
        state.textContent = result.passed
          ? "Пройден"
          : `${result.actual_action} · ${result.actual_rule_id}`;
        row.append(name, state);
        list.appendChild(row);
      }
      setStatus(
        status,
        report.failed ? `Есть ошибки: ${report.failed}` : "Все сценарии пройдены",
        report.failed ? "err" : "ok"
      );
    } catch (error) {
      setStatus(status, `Ошибка: ${error.message}`, "err");
    } finally {
      button.disabled = false;
    }
  }

  async function resetMetrics() {
    const confirmed = confirm(
      "Сбросить агрегированные счётчики Safety Policy? Правила и настройки не изменятся."
    );
    if (!confirmed) return;
    const status = byId("safety-policy-status");
    try {
      render(await api("/api/safety-policy/metrics", { method: "DELETE" }));
      setStatus(status, "Счётчики сброшены", "ok");
    } catch (error) {
      setStatus(status, `Ошибка: ${error.message}`, "err");
    }
  }

  byId("safety-policy-refresh").onclick = load;
  byId("safety-run-scenarios").onclick = runScenarios;
  byId("safety-reset-metrics").onclick = resetMetrics;
  byId("safety-open-agents").onclick = openAgents;
  return { load };
}
