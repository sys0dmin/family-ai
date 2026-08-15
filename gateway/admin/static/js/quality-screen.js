import { api, requestBlob } from "./api-client.js?v=admin-modules-2";
import { byId, formatDateTime, getValue, setStatus, setValue } from "./dom.js?v=admin-modules-2";

export const feedbackReasonLabels = {
  factual_error: "Фактическая ошибка",
  misunderstood: "Не понял вопрос",
  too_complex: "Слишком сложно",
  false_block: "Ложная блокировка",
  character_break: "Нарушен характер",
  bad_voice: "Плохой голос",
  bad_vision: "Ошибка Vision",
  other: "Другая проблема"
};

export function createQualityScreen({ reloadHistory }) {
  let currentMessage = null;
  let currentFeedback = null;
  let sourceFeedbackId = null;

  async function loadSummary(days = getValue("history-days")) {
    try {
      const data = await api(`/api/quality/summary?days=${days}`, {
        method: "GET"
      });
      byId("quality-feedback-total").textContent = data.total_feedback;
      byId("quality-case-total").textContent = data.regression_cases;
      const reasons = byId("quality-reason-list");
      reasons.replaceChildren();
      if (!data.reasons.length) {
        const empty = document.createElement("span");
        empty.className = "muted";
        empty.textContent = "Проблем пока не отмечено";
        reasons.append(empty);
      }
      for (const item of data.reasons) {
        const badge = document.createElement("span");
        badge.className = "quality-reason-badge";
        badge.textContent = `${feedbackReasonLabels[item.reason] || item.reason} · ${item.count}`;
        reasons.append(badge);
      }
      byId("quality-summary-status").textContent = `Последние ${data.days} дн.`;
    } catch (error) {
      byId("quality-summary-status").textContent = `Ошибка: ${error.message}`;
    }
  }

  function openFeedback(message) {
    currentMessage = message;
    currentFeedback = message.feedback || null;
    byId("feedback-message").textContent = message.content;
    setValue("feedback-reason", currentFeedback?.reason || "factual_error");
    setValue("feedback-note", currentFeedback?.note || "");
    byId("feedback-delete").hidden = !currentFeedback;
    byId("feedback-to-regression").hidden = message.role !== "assistant";
    byId("feedback-status").textContent = "";
    byId("feedback-dialog").showModal();
  }

  async function saveFeedback() {
    if (!currentMessage) return null;
    const result = await api("/api/quality/feedback", {
      method: "POST",
      body: JSON.stringify({
        message_id: currentMessage.id,
        reason: getValue("feedback-reason"),
        note: getValue("feedback-note").trim() || null
      })
    });
    currentFeedback = result;
    currentMessage.feedback = result;
    byId("feedback-delete").hidden = false;
    await Promise.all([reloadHistory(), loadSummary()]);
    return result;
  }

  async function handleSaveFeedback() {
    const status = byId("feedback-status");
    try {
      setStatus(status, "Сохраняем…", "warn");
      await saveFeedback();
      setStatus(status, "Отметка сохранена", "ok");
    } catch (error) {
      setStatus(status, `Ошибка: ${error.message}`, "err");
    }
  }

  async function deleteFeedback() {
    if (!currentFeedback || !confirm("Удалить эту отметку проблемы?")) return;
    try {
      await api(`/api/quality/feedback/${currentFeedback.id}`, {
        method: "DELETE"
      });
      byId("feedback-dialog").close();
      currentFeedback = null;
      await Promise.all([reloadHistory(), loadSummary(), loadCases()]);
    } catch (error) {
      setStatus(byId("feedback-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  async function prepareRegressionCase() {
    try {
      setStatus(byId("feedback-status"), "Готовим полный текст…", "warn");
      const feedback = await saveFeedback();
      const preview = await api(
        `/api/quality/feedback/${feedback.id}/regression-preview`,
        { method: "GET" }
      );
      sourceFeedbackId = preview.source_feedback_id;
      setValue("regression-title", preview.title);
      setValue("regression-agent", preview.agent_id);
      setValue("regression-prompt", preview.prompt);
      setValue("regression-expected", preview.expected_response);
      setValue("regression-safety", preview.expected_safety_status);
      setValue("regression-rule", preview.expected_safety_rule_id || "");
      setValue("regression-error", preview.expected_technical_error);
      byId("regression-confirm").checked = false;
      byId("regression-dialog-status").textContent = "";
      byId("feedback-dialog").close();
      byId("regression-dialog").showModal();
    } catch (error) {
      setStatus(byId("feedback-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  async function saveRegressionCase() {
    const status = byId("regression-dialog-status");
    if (!byId("regression-confirm").checked) {
      setStatus(status, "Подтвердите, что просмотрели весь текст", "warn");
      return;
    }
    try {
      setStatus(status, "Сохраняем подтверждённую копию…", "warn");
      await api("/api/quality/regression-cases", {
        method: "POST",
        body: JSON.stringify({
          confirmed: true,
          source_feedback_id: sourceFeedbackId,
          agent_id: getValue("regression-agent"),
          title: getValue("regression-title"),
          prompt: getValue("regression-prompt"),
          expected_response: getValue("regression-expected"),
          expected_safety_status: getValue("regression-safety"),
          expected_safety_rule_id: getValue("regression-rule").trim() || null,
          expected_technical_error: getValue("regression-error")
        })
      });
      byId("regression-dialog").close();
      await Promise.all([loadCases(), loadSummary()]);
    } catch (error) {
      setStatus(status, `Ошибка: ${error.message}`, "err");
    }
  }

  function comparisonText(comparison) {
    const checks = [
      ["ответ", comparison.response_matches],
      ["safety", comparison.safety_status_matches],
      ["rule", comparison.safety_rule_matches],
      ["ошибка", comparison.technical_error_matches]
    ];
    return checks.map(([label, passed]) => `${passed ? "✓" : "×"} ${label}`).join(" · ");
  }

  function renderCases(data) {
    const list = byId("regression-list");
    list.replaceChildren();
    if (!data.items.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Подтверждённых проверок пока нет";
      list.append(empty);
      return;
    }
    for (const item of data.items) {
      const card = document.createElement("article");
      card.className = "regression-case";
      const head = document.createElement("div");
      head.className = "regression-case-head";
      const identity = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = item.title;
      const meta = document.createElement("div");
      meta.className = "muted";
      meta.textContent = `${item.agent_id} · ${formatDateTime(item.created_at)}`;
      identity.append(title, meta);
      const actions = document.createElement("div");
      actions.className = "row card-actions";
      const run = document.createElement("button");
      run.className = "primary";
      run.textContent = "▶ Запустить";
      const remove = document.createElement("button");
      remove.className = "secondary";
      remove.textContent = "Удалить";
      actions.append(run, remove);
      head.append(identity, actions);
      const prompt = document.createElement("div");
      prompt.className = "regression-prompt";
      prompt.textContent = item.prompt;
      const expectation = document.createElement("div");
      expectation.className = "regression-expectation muted";
      expectation.textContent =
        `Ожидается: ${item.expected_safety_status}` +
        `${item.expected_safety_rule_id ? ` · ${item.expected_safety_rule_id}` : ""}` +
        ` · ${item.expected_technical_error}`;
      const result = document.createElement("div");
      result.className = "regression-result";
      result.hidden = true;
      run.onclick = async () => {
        run.disabled = true;
        result.hidden = false;
        result.textContent = "Модель думает…";
        try {
          const response = await api(
            `/api/quality/regression-cases/${item.id}/run`,
            { method: "POST" }
          );
          result.className = `regression-result ${response.comparison.overall_matches ? "passed" : "failed"}`;
          result.textContent =
            `${comparisonText(response.comparison)}\n\n` +
            `Фактический ответ:\n${response.actual_response || "—"}`;
        } catch (error) {
          result.className = "regression-result failed";
          result.textContent = `Ошибка запуска: ${error.message}`;
        } finally {
          run.disabled = false;
        }
      };
      remove.onclick = async () => {
        if (!confirm(`Удалить проверку «${item.title}»?`)) return;
        await api(`/api/quality/regression-cases/${item.id}`, {
          method: "DELETE"
        });
        await Promise.all([loadCases(), loadSummary()]);
      };
      card.append(head, prompt, expectation, result);
      list.append(card);
    }
  }

  async function loadCases() {
    try {
      const data = await api("/api/quality/regression-cases", { method: "GET" });
      renderCases(data);
      setStatus(byId("regression-status"), `${data.total} проверок`, "ok");
    } catch (error) {
      setStatus(byId("regression-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  async function exportCases() {
    try {
      const blob = await requestBlob("/api/quality/regression-cases-export", {
        method: "GET"
      });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "family-ai-regression-cases.json";
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      setStatus(byId("regression-status"), `Ошибка экспорта: ${error.message}`, "err");
    }
  }

  byId("feedback-save").onclick = handleSaveFeedback;
  byId("feedback-delete").onclick = deleteFeedback;
  byId("feedback-to-regression").onclick = prepareRegressionCase;
  byId("regression-save").onclick = saveRegressionCase;
  byId("regression-refresh").onclick = loadCases;
  byId("regression-export").onclick = exportCases;

  return { openFeedback, loadSummary, loadCases };
}
