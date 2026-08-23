import { api } from "./api-client.js?v=admin-modules-2";
import {
  formatDateTime,
  getValue,
  setStatus,
  setValue
} from "./dom.js?v=admin-modules-3";

const KNOWN_TTS_VOICES = new Set([
  "xenia", "baya", "kseniya", "aidar", "eugene",
  "lulwa", "noura", "aisha", "abdullah", "fahad", "sultan"
]);

export function createSettingsScreen() {
  let pendingPayload = null;

  function setSaveStatus(text, mode) {
    setStatus(document.getElementById("save-status"), text, mode);
  }

  function applyTtsVoice(value) {
    const customField = document.getElementById("tts_voice_custom_field");
    if (KNOWN_TTS_VOICES.has(value)) {
      setValue("tts_voice", value);
      setValue("tts_voice_custom", "");
      customField.hidden = true;
      return;
    }
    setValue("tts_voice", "__custom__");
    setValue("tts_voice_custom", value);
    customField.hidden = false;
  }

  function getTtsVoice() {
    const selected = getValue("tts_voice");
    return selected === "__custom__"
      ? getValue("tts_voice_custom").trim()
      : selected;
  }

  function updateProviderBadge(id, enabled, enabledText) {
    const badge = document.getElementById(id);
    badge.querySelector("span").textContent = enabled ? enabledText : "Выключено";
    badge.querySelector("i").className = `signal-dot ${enabled ? "cyan" : ""}`;
  }

  function apply(data) {
    setValue("openai_model", data.openai_model);
    setValue("openai_base_url", data.openai_base_url || "");
    setValue("web_search_tool_type", data.web_search_tool_type || "disabled");
    setValue("image_search_provider", data.image_search_provider || "disabled");
    setValue("image_search_timeout_seconds", data.image_search_timeout_seconds || 6);
    setValue("vision_provider", data.vision_provider || "disabled");
    setValue("vision_base_url", data.vision_base_url || "");
    setValue("vision_model", data.vision_model || "qwen/qwen3.6-27b");
    setValue(
      "vision_max_image_mb",
      Math.max(1, Math.round((data.vision_max_image_bytes || 10485760) / 1048576))
    );
    setValue("vision_api_key", "");
    document.getElementById("clear_vision_api_key").checked = false;
    setValue("speech_base_url", data.speech_base_url || "");
    setValue("stt_base_url", data.stt_base_url || "");
    setValue("tts_base_url", data.tts_base_url || "");
    setValue("stt_model", data.stt_model);
    setValue("stt_initial_prompt", data.stt_initial_prompt);
    setValue("tts_model", data.tts_model);
    applyTtsVoice(data.tts_voice);
    setValue("tts_response_format", data.tts_response_format);
    setValue("message_retention_days", data.message_retention_days);
    setValue("voice_max_in_flight", data.voice_max_in_flight || 2);
    setValue("voice_stt_timeout_seconds", data.voice_stt_timeout_seconds || 60);
    setValue("voice_llm_timeout_seconds", data.voice_llm_timeout_seconds || 20);
    setValue("voice_tts_timeout_seconds", data.voice_tts_timeout_seconds || 30);
    for (const id of [
      "openai_api_key", "speech_api_key", "stt_api_key", "tts_api_key",
      "acrcloud_access_key", "acrcloud_access_secret"
    ]) setValue(id, "");
    document.getElementById("clear_stt_api_key").checked = false;
    document.getElementById("clear_tts_api_key").checked = false;
    setValue("music_recognition_provider", data.music_recognition_provider || "disabled");
    setValue("acrcloud_host", data.acrcloud_host || "");
    setValue("music_recognition_timeout_seconds", data.music_recognition_timeout_seconds || 8);
    updateProviderBadge(
      "music-provider-badge",
      data.music_recognition_provider === "acrcloud",
      "ACRCloud"
    );
    updateProviderBadge(
      "image-provider-badge",
      data.image_search_provider === "openverse",
      "Openverse"
    );
    updateProviderBadge(
      "vision-provider-badge",
      data.vision_provider === "openai_compatible",
      "Включено"
    );
    document.getElementById("summary").textContent =
      `env=${data.environment}, LLM=${data.openai_api_key_preview || "(empty)"}, STT=${data.stt_api_key_preview || data.speech_api_key_preview || "(fallback LLM)"}, TTS=${data.tts_api_key_preview || data.speech_api_key_preview || "(fallback LLM)"}, images=${data.image_search_provider || "disabled"}, vision=${data.vision_provider || "disabled"}, melody=${data.music_recognition_provider || "disabled"}`;
    document.getElementById("environment-label").textContent = data.environment;
    document.querySelector(".retention-ring").textContent = `${data.message_retention_days}d`;
  }

  function collectPayload() {
    return {
      openai_model: getValue("openai_model").trim(),
      openai_base_url: getValue("openai_base_url").trim() || null,
      web_search_tool_type: getValue("web_search_tool_type"),
      image_search_provider: getValue("image_search_provider"),
      image_search_timeout_seconds: Number(getValue("image_search_timeout_seconds")),
      vision_provider: getValue("vision_provider"),
      vision_base_url: getValue("vision_base_url").trim() || null,
      vision_model: getValue("vision_model").trim(),
      vision_max_image_bytes: Math.round(Number(getValue("vision_max_image_mb")) * 1048576),
      vision_api_key: getValue("vision_api_key").trim() || null,
      clear_vision_api_key: document.getElementById("clear_vision_api_key").checked,
      speech_base_url: getValue("speech_base_url").trim() || null,
      stt_base_url: getValue("stt_base_url").trim() || null,
      tts_base_url: getValue("tts_base_url").trim() || null,
      stt_model: getValue("stt_model").trim(),
      stt_initial_prompt: getValue("stt_initial_prompt").trim(),
      tts_model: getValue("tts_model").trim(),
      tts_voice: getTtsVoice(),
      tts_response_format: getValue("tts_response_format"),
      message_retention_days: Number(getValue("message_retention_days")),
      voice_max_in_flight: Number(getValue("voice_max_in_flight")),
      voice_stt_timeout_seconds: Number(getValue("voice_stt_timeout_seconds")),
      voice_llm_timeout_seconds: Number(getValue("voice_llm_timeout_seconds")),
      voice_tts_timeout_seconds: Number(getValue("voice_tts_timeout_seconds")),
      openai_api_key: getValue("openai_api_key").trim() || null,
      speech_api_key: getValue("speech_api_key").trim() || null,
      stt_api_key: getValue("stt_api_key").trim() || null,
      tts_api_key: getValue("tts_api_key").trim() || null,
      clear_stt_api_key: document.getElementById("clear_stt_api_key").checked,
      clear_tts_api_key: document.getElementById("clear_tts_api_key").checked,
      music_recognition_provider: getValue("music_recognition_provider"),
      acrcloud_host: getValue("acrcloud_host").trim() || null,
      acrcloud_access_key: getValue("acrcloud_access_key").trim() || null,
      acrcloud_access_secret: getValue("acrcloud_access_secret").trim() || null,
      music_recognition_timeout_seconds: Number(getValue("music_recognition_timeout_seconds"))
    };
  }

  function renderChanges(changes) {
    const list = document.getElementById("config-preview-list");
    list.replaceChildren();
    for (const change of changes) {
      const row = document.createElement("div");
      row.className = "config-change";
      const key = document.createElement("strong");
      key.textContent = change.key.replaceAll("_", " ");
      const before = document.createElement("span");
      before.textContent = change.before;
      const arrow = document.createElement("i");
      arrow.textContent = "→";
      const after = document.createElement("span");
      after.textContent = change.after;
      row.append(key, before, arrow, after);
      list.append(row);
    }
  }

  async function preview() {
    const button = document.getElementById("save-btn");
    button.disabled = true;
    setSaveStatus("Проверяем конфигурацию…", "warn");
    try {
      const payload = collectPayload();
      const result = await api("/api/settings/preview", {
        method: "POST",
        body: JSON.stringify(payload)
      });
      if (!result.changes.length) {
        setSaveStatus("Изменений нет", "ok");
        return;
      }
      pendingPayload = payload;
      renderChanges(result.changes);
      document.getElementById("config-preview-dialog").showModal();
      setSaveStatus(`Проверено изменений: ${result.changes.length}`, "ok");
    } catch (error) {
      setSaveStatus(`Проверка не пройдена: ${error.message}`, "err");
    } finally {
      button.disabled = false;
    }
  }

  async function applyPending(event) {
    event.preventDefault();
    if (!pendingPayload) return;
    const button = document.getElementById("config-preview-apply");
    button.disabled = true;
    setSaveStatus("Сохраняем, перезапускаем Gateway и ждём health-check…", "warn");
    try {
      const data = await api("/api/settings", {
        method: "POST",
        body: JSON.stringify(pendingPayload)
      });
      pendingPayload = null;
      document.getElementById("config-preview-dialog").close();
      apply(data);
      await loadRevisions();
      setSaveStatus("Применено: Gateway перезапущен и прошёл health-check", "ok");
    } catch (error) {
      setSaveStatus(`Изменения отклонены: ${error.message}`, "err");
    } finally {
      button.disabled = false;
    }
  }

  async function rollback(revision) {
    if (!confirm(`Вернуть конфигурацию ${revision.id}? Gateway будет перезапущен и проверен.`)) return;
    setSaveStatus("Восстанавливаем выбранную ревизию…", "warn");
    try {
      await api(`/api/settings/revisions/${encodeURIComponent(revision.id)}/rollback`, {
        method: "POST"
      });
      await load();
      await loadRevisions();
      setSaveStatus("Ревизия восстановлена, Gateway прошёл health-check", "ok");
    } catch (error) {
      setSaveStatus(`Rollback не выполнен: ${error.message}`, "err");
    }
  }

  async function loadRevisions() {
    const list = document.getElementById("config-revision-list");
    try {
      const data = await api("/api/settings/revisions", { method: "GET" });
      list.replaceChildren();
      if (!data.items.length) {
        const empty = document.createElement("span");
        empty.className = "muted";
        empty.textContent = "Первая ревизия появится после применения настроек";
        list.append(empty);
        return;
      }
      for (const revision of data.items) {
        const row = document.createElement("div");
        row.className = `config-revision${revision.status === "active" ? " active" : ""}`;
        const copy = document.createElement("div");
        copy.className = "config-revision-copy";
        const title = document.createElement("strong");
        title.textContent = `${revision.operation} · ${revision.id}`;
        if (revision.status === "active") {
          const badge = document.createElement("span");
          badge.className = "config-revision-badge";
          badge.textContent = "active";
          title.append(badge);
        }
        const meta = document.createElement("small");
        meta.textContent = `${formatDateTime(revision.created_at)} · ${revision.actor} · ${revision.fingerprint} · изменений ${revision.changes.length}`;
        copy.append(title, meta);
        row.append(copy);
        if (revision.status === "superseded") {
          const action = document.createElement("button");
          action.className = "secondary";
          action.textContent = "Вернуть";
          action.onclick = () => rollback(revision);
          row.append(action);
        }
        list.append(row);
      }
    } catch (error) {
      list.textContent = `История недоступна: ${error.message}`;
    }
  }

  async function load() {
    const data = await api("/api/settings", { method: "GET" });
    apply(data);
    return data;
  }

  document.getElementById("config-revisions-reload").onclick = loadRevisions;
  document.getElementById("config-preview-apply").onclick = applyPending;
  document.getElementById("save-btn").onclick = preview;
  document.getElementById("tts_voice").onchange = () => {
    const customInput = document.getElementById("tts_voice_custom");
    const customField = document.getElementById("tts_voice_custom_field");
    customField.hidden = getValue("tts_voice") !== "__custom__";
    if (!customField.hidden) customInput.focus();
  };

  return { load, loadRevisions, setSaveStatus };
}
