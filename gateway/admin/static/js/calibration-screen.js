import { api } from "./api-client.js?v=admin-modules-2";
import {
  formatPipelineMs,
  getValue,
  setStatus,
  setValue
} from "./dom.js?v=admin-modules-3";

export function createCalibrationScreen() {
  function render(state) {
    const stateLabel = document.getElementById("calibration-state");
    const startButton = document.getElementById("calibration-start");
    const cancelButton = document.getElementById("calibration-cancel");
    const results = document.getElementById("calibration-results");
    results.replaceChildren();
    if (!state) {
      stateLabel.textContent = "Не запускалась";
      startButton.disabled = false;
      cancelButton.hidden = true;
      document.getElementById("calibration-samples").textContent = "0 / 15";
      document.getElementById("calibration-trials").textContent = "0 / 90";
      document.getElementById("calibration-progress-bar").style.width = "0%";
      document.getElementById("calibration-recommendation").textContent = "";
      return;
    }
    const labels = {
      collecting: "Ждём Леру",
      running: "Идёт анализ",
      completed: "Готово",
      failed: "Ошибка",
      cancelled: "Отменено"
    };
    stateLabel.textContent = labels[state.status] || state.status;
    startButton.disabled = ["collecting", "running"].includes(state.status);
    cancelButton.hidden = !["collecting", "running"].includes(state.status);
    cancelButton.dataset.sessionId = state.id;
    document.getElementById("calibration-samples").textContent =
      `${state.samples_collected} / ${state.prompts_total}`;
    document.getElementById("calibration-trials").textContent =
      `${state.current_trial} / ${state.total_trials}`;
    const progress = state.status === "collecting"
      ? state.samples_collected / Math.max(1, state.prompts_total)
      : state.current_trial / Math.max(1, state.total_trials);
    document.getElementById("calibration-progress-bar").style.width =
      `${Math.round(progress * 100)}%`;
    document.getElementById("calibration-recommendation").textContent =
      state.recommended_beam_size == null
        ? (state.error || "")
        : `Рекомендация: VAD ${state.recommended_vad_filter ? "вкл." : "выкл."}, beam ${state.recommended_beam_size}`;
    for (const item of state.results || []) {
      const row = document.createElement("tr");
      for (const value of [
        item.vad_filter ? "Вкл." : "Выкл.",
        item.beam_size,
        `${item.spoken_accuracy_percent}%`,
        `${item.silence_rejection_percent}%`,
        formatPipelineMs(item.average_processing_ms),
        formatPipelineMs(item.p95_processing_ms)
      ]) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      }
      results.append(row);
    }
  }

  async function loadRuntimeSettings() {
    const status = document.getElementById("speech-runtime-status");
    try {
      const settings = await api("/api/speech/runtime-settings", { method: "GET" });
      setValue("speech-runtime-beam", settings.stt_beam_size);
      document.getElementById("speech-runtime-vad").checked = settings.stt_vad_filter;
      setValue("speech-runtime-max-tokens", settings.stt_max_new_tokens);
      document.getElementById("speech-runtime-state").textContent =
        `beam ${settings.stt_beam_size} · VAD ${settings.stt_vad_filter ? "вкл." : "выкл."} · ${settings.stt_max_new_tokens} токенов`;
      setStatus(status, "Значения загружены из Speech", "ok");
    } catch (error) {
      document.getElementById("speech-runtime-state").textContent = "Недоступно";
      setStatus(status, `Ошибка: ${error.message}`, "err");
    }
  }

  async function applyRuntimeSettings() {
    const button = document.getElementById("speech-runtime-apply");
    const beam = Number.parseInt(getValue("speech-runtime-beam"), 10);
    const vad = document.getElementById("speech-runtime-vad").checked;
    const maxTokens = Number.parseInt(getValue("speech-runtime-max-tokens"), 10);
    if (!confirm(`Применить beam ${beam}, VAD ${vad ? "вкл." : "выкл."}, лимит ${maxTokens} токенов и перезапустить Speech? Голос будет недоступен около 15 секунд.`)) return;
    button.disabled = true;
    setStatus(
      document.getElementById("speech-runtime-status"),
      "Сохраняем и ждём новый процесс Speech…",
      ""
    );
    try {
      const settings = await api("/api/speech/runtime-settings", {
        method: "PUT",
        body: JSON.stringify({
          stt_beam_size: beam,
          stt_vad_filter: vad,
          stt_max_new_tokens: maxTokens
        })
      });
      document.getElementById("speech-runtime-state").textContent =
        `beam ${settings.stt_beam_size} · VAD ${settings.stt_vad_filter ? "вкл." : "выкл."} · ${settings.stt_max_new_tokens} токенов`;
      setStatus(
        document.getElementById("speech-runtime-status"),
        "Speech перезапущен, настройки подтверждены",
        "ok"
      );
    } catch (error) {
      setStatus(
        document.getElementById("speech-runtime-status"),
        `Ошибка: ${error.message}`,
        "err"
      );
    } finally {
      button.disabled = false;
    }
  }

  async function loadStatus() {
    try {
      const state = await api("/api/stt-calibration/status", { method: "GET" });
      render(state);
    } catch (error) {
      setStatus(
        document.getElementById("calibration-status"),
        `Недоступно: ${error.message}`,
        "err"
      );
    }
  }

  async function start() {
    if (!confirm("Начать локальную калибровку? После этого откройте Android-приложение и передайте телефон Лере.")) return;
    const button = document.getElementById("calibration-start");
    button.disabled = true;
    try {
      const state = await api("/api/stt-calibration/start", { method: "POST" });
      render(state);
      setStatus(
        document.getElementById("calibration-status"),
        "Сессия готова. Откройте приложение.",
        "ok"
      );
    } catch (error) {
      setStatus(document.getElementById("calibration-status"), `Ошибка: ${error.message}`, "err");
      button.disabled = false;
    }
  }

  async function cancel() {
    const button = document.getElementById("calibration-cancel");
    const sessionId = button.dataset.sessionId;
    if (!sessionId || !confirm("Отменить калибровку и удалить записанные WAV?")) return;
    try {
      const state = await api(
        `/api/stt-calibration/${encodeURIComponent(sessionId)}`,
        { method: "DELETE" }
      );
      render(state);
      setStatus(document.getElementById("calibration-status"), "Записи удалены", "ok");
    } catch (error) {
      setStatus(document.getElementById("calibration-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  document.getElementById("calibration-start").onclick = start;
  document.getElementById("calibration-cancel").onclick = cancel;
  document.getElementById("speech-runtime-apply").onclick = applyRuntimeSettings;

  return { loadRuntimeSettings, loadStatus, render };
}
