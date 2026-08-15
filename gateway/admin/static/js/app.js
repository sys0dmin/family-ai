    import {
      api,
      createBrowserSession,
      deleteBrowserSession,
      requestBlob
    } from "./api-client.js";
    import { formatDateTime, getValue, setStatus, setValue } from "./dom.js";
    import { createHistoryScreen } from "./history-screen.js";
    import { createInfrastructureScreen } from "./infrastructure-screen.js";
    import { createActivityScreen } from "./activity-screen.js";
    import { createMemoryScreen } from "./memory-screen.js";
    import { createNavigation, hideAllScreens } from "./navigation.js";
    import { createQualityScreen } from "./quality-screen.js";
    import { createSafetyPolicyScreen } from "./safety-policy-screen.js";

    const authCard = document.getElementById("auth-card");
    const passwordCard = document.getElementById("password-card");
    const mainNav = document.getElementById("main-nav");
    const authStatus = document.getElementById("auth-status");
    const passwordStatus = document.getElementById("password-status");
    const saveStatus = document.getElementById("save-status");
    const summary = document.getElementById("summary");
    const knownTtsVoices = new Set(["xenia", "baya", "kseniya", "aidar", "eugene", "lulwa", "noura", "aisha", "abdullah", "fahad", "sultan"]);
    let agents = [];
    let selectedAgentId = null;
    let infrastructureTimer = null;
    let calibrationTimer = null;
    let pendingSettingsPayload = null;
    let navigate;

    function setSaveStatus(text, mode) {
      setStatus(saveStatus, text, mode);
    }

    function applyTtsVoice(value) {
      const customInput = document.getElementById("tts_voice_custom");
      const customField = document.getElementById("tts_voice_custom_field");
      if (knownTtsVoices.has(value)) {
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

    function switchTab(tab) {
      navigate(tab);
    }

    function selectedAgent() {
      return agents.find(agent => agent.id === selectedAgentId) || null;
    }

    function renderAgentList() {
      const list = document.getElementById("agent-list");
      list.replaceChildren();
      for (const agent of agents) {
        const button = document.createElement("button");
        button.className = `agent-list-button${agent.id === selectedAgentId ? " active" : ""}`;
        button.style.setProperty("--agent-color", agent.color || "var(--violet)");
        const icon = document.createElement("span");
        icon.className = "agent-icon";
        icon.textContent = agent.icon;
        const label = document.createElement("span");
        const name = document.createElement("strong");
        name.textContent = agent.display_name;
        const state = document.createElement("div");
        state.className = "muted";
        state.textContent = agent.enabled ? "Доступен" : "Отключён";
        label.append(name, state);
        button.append(icon, label);
        button.onclick = () => {
          selectedAgentId = agent.id;
          renderAgentList();
          renderAgentEditor();
        };
        list.append(button);
      }
    }

    function renderAgentEditor() {
      const agent = selectedAgent();
      const editor = document.getElementById("agent-editor");
      editor.style.display = agent ? "block" : "none";
      if (!agent) return;

      setValue("agent-name", agent.display_name);
      setValue("agent-icon", agent.icon);
      setValue("agent-color", agent.color);
      setValue("agent-voice", agent.tts_voice || "lulwa");
      setValue("agent-order", agent.sort_order);
      setValue("agent-enabled", String(agent.enabled));
      setValue("agent-description", agent.description);
      setValue("agent-greeting", agent.greeting);
      document.getElementById("agent-tool-music").checked = (agent.tools || []).includes("music_recognition");
      document.getElementById("agent-tool-web-search").checked = (agent.tools || []).includes("web_search");
      document.getElementById("agent-tool-image-search").checked = (agent.tools || []).includes("image_search");
      document.getElementById("agent-tool-image-understanding").checked = (agent.tools || []).includes("image_understanding");
      document.getElementById("agent-permission-outdoor").checked = (agent.permissions || []).includes("supervised_outdoor_safety");
      setValue("agent-new-prompt", agent.revisions[0]?.system_prompt || "");

      const revisions = document.getElementById("agent-revisions");
      revisions.replaceChildren();
      for (const revision of agent.revisions) {
        const card = document.createElement("div");
        card.className = `revision${revision.is_active ? " active" : ""}`;
        const head = document.createElement("div");
        head.className = "revision-head";
        const meta = document.createElement("strong");
        meta.textContent = `Версия ${revision.version}${revision.is_active ? " · опубликована" : ""}`;
        const action = document.createElement("button");
        action.className = "secondary";
        action.textContent = revision.is_active ? "Активна" : "Опубликовать";
        action.disabled = revision.is_active;
        action.onclick = () => publishAgentRevision(revision.id, revision.version);
        head.append(meta, action);
        const byline = document.createElement("div");
        byline.className = "muted";
        byline.textContent = `${formatDateTime(revision.created_at)} · ${revision.created_by}`;
        const prompt = document.createElement("div");
        prompt.className = "revision-prompt";
        prompt.textContent = revision.system_prompt;
        card.append(head, byline, prompt);
        revisions.append(card);
      }
    }

    async function loadAgents() {
      const status = document.getElementById("agents-status");
      setStatus(status, "Загрузка…", "warn");
      try {
        const data = await api("/api/agents", { method: "GET" });
        agents = data.items;
        setValue("safety-baseline", data.safety_baseline);
        document.getElementById("safety-baseline-meta").textContent = data.safety_baseline_version
          ? `Версия ${data.safety_baseline_version} · ${data.safety_baseline_updated_by} · ${formatDateTime(data.safety_baseline_updated_at)}`
          : "Резервная версия из кода";
        if (!selectedAgentId || !agents.some(agent => agent.id === selectedAgentId)) {
          selectedAgentId = agents[0]?.id || null;
        }
        renderAgentList();
        renderAgentEditor();
        populateStudioAgents();
        setStatus(status, "Обновлено", "ok");
      } catch (error) {
        setStatus(status, `Ошибка: ${error.message}`, "err");
      }
    }

    function populateStudioAgents() {
      const select = document.getElementById("studio-agent");
      const previous = select.value;
      select.replaceChildren();
      for (const agent of agents.filter(item => item.enabled)) {
        const option = document.createElement("option");
        option.value = agent.id;
        option.textContent = `${agent.icon} ${agent.display_name}`;
        select.append(option);
      }
      if ([...select.options].some(option => option.value === previous)) {
        select.value = previous;
      }
      syncStudioVoice();
    }

    function syncStudioVoice() {
      const agent = agents.find(item => item.id === getValue("studio-agent"));
      if (agent?.tts_voice && knownTtsVoices.has(agent.tts_voice)) {
        setValue("studio-voice", agent.tts_voice);
      }
    }

    async function loadStudio() {
      if (!agents.length) await loadAgents();
      populateStudioAgents();
    }

    async function runStudioTest() {
      const status = document.getElementById("studio-status");
      const button = document.getElementById("studio-run");
      const prompt = getValue("studio-prompt").trim();
      if (!prompt) {
        setStatus(status, "Напиши тестовый вопрос", "warn");
        return;
      }
      button.disabled = true;
      setStatus(status, "Модель думает…", "warn");
      try {
        const result = await api("/api/studio/agent-test", {
          method: "POST",
          body: JSON.stringify({ agent_id: getValue("studio-agent"), prompt })
        });
        document.getElementById("studio-raw").textContent = result.raw_response || "Модель не вызывалась";
        document.getElementById("studio-final").textContent = result.final_response || "—";
        document.getElementById("studio-safety").textContent =
          result.safety_status === "passed" ? "Safety passed" :
          result.safety_status === "guardrail" ? "Guardrail" : "Blocked";
        document.getElementById("studio-timing").textContent =
          result.llm_duration_ms == null ? "LLM не вызывалась" : `LLM ${result.llm_duration_ms} мс`;
        document.getElementById("studio-rule").textContent =
          result.safety_rule_id ? `${result.safety_rule_id}: ${result.safety_reason || ""}` : "";
        setValue("studio-speech-text", result.final_response || "");
        setStatus(status, "Проверка завершена", result.safety_status === "blocked" ? "warn" : "ok");
      } catch (error) {
        setStatus(status, `Ошибка: ${error.message}`, "err");
      } finally {
        button.disabled = false;
      }
    }

    async function speakStudioText() {
      const status = document.getElementById("studio-status");
      const button = document.getElementById("studio-speak");
      const text = getValue("studio-speech-text").trim();
      if (!text) {
        setStatus(status, "Нет текста для озвучки", "warn");
        return;
      }
      button.disabled = true;
      setStatus(status, "Синтезируем речь…", "warn");
      try {
        const blob = await requestBlob("/api/studio/speech", {
          method: "POST",
          body: JSON.stringify({ text, voice: getValue("studio-voice") })
        });
        const audio = document.getElementById("studio-audio");
        if (audio.dataset.objectUrl) URL.revokeObjectURL(audio.dataset.objectUrl);
        const objectUrl = URL.createObjectURL(blob);
        audio.dataset.objectUrl = objectUrl;
        audio.src = objectUrl;
        await audio.play();
        setStatus(status, "Голос готов", "ok");
      } catch (error) {
        setStatus(status, `Ошибка TTS: ${error.message}`, "err");
      } finally {
        button.disabled = false;
      }
    }

    function renderCalibration(state) {
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

    async function loadSpeechRuntimeSettings() {
      const status = document.getElementById("speech-runtime-status");
      try {
        const settings = await api("/api/speech/runtime-settings", { method: "GET" });
        setValue("speech-runtime-beam", settings.stt_beam_size);
        document.getElementById("speech-runtime-vad").checked = settings.stt_vad_filter;
        document.getElementById("speech-runtime-state").textContent =
          `beam ${settings.stt_beam_size} · VAD ${settings.stt_vad_filter ? "вкл." : "выкл."}`;
        setStatus(status, "Значения загружены из Speech", "ok");
      } catch (error) {
        document.getElementById("speech-runtime-state").textContent = "Недоступно";
        setStatus(status, `Ошибка: ${error.message}`, "err");
      }
    }

    async function applySpeechRuntimeSettings() {
      const button = document.getElementById("speech-runtime-apply");
      const beam = Number.parseInt(getValue("speech-runtime-beam"), 10);
      const vad = document.getElementById("speech-runtime-vad").checked;
      if (!confirm(`Применить beam ${beam}, VAD ${vad ? "вкл." : "выкл."} и перезапустить Speech? Голос будет недоступен около 15 секунд.`)) return;
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
            stt_vad_filter: vad
          })
        });
        document.getElementById("speech-runtime-state").textContent =
          `beam ${settings.stt_beam_size} · VAD ${settings.stt_vad_filter ? "вкл." : "выкл."}`;
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

    async function loadCalibrationStatus() {
      try {
        const state = await api("/api/stt-calibration/status", { method: "GET" });
        renderCalibration(state);
      } catch (error) {
        setStatus(
          document.getElementById("calibration-status"),
          `Недоступно: ${error.message}`,
          "err"
        );
      }
    }

    async function startCalibration() {
      if (!confirm("Начать локальную калибровку? После этого откройте Android-приложение и передайте телефон Лере.")) return;
      const button = document.getElementById("calibration-start");
      button.disabled = true;
      try {
        const state = await api("/api/stt-calibration/start", { method: "POST" });
        renderCalibration(state);
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

    async function cancelCalibration() {
      const button = document.getElementById("calibration-cancel");
      const sessionId = button.dataset.sessionId;
      if (!sessionId || !confirm("Отменить калибровку и удалить записанные WAV?")) return;
      try {
        const state = await api(
          `/api/stt-calibration/${encodeURIComponent(sessionId)}`,
          { method: "DELETE" }
        );
        renderCalibration(state);
        setStatus(document.getElementById("calibration-status"), "Записи удалены", "ok");
      } catch (error) {
        setStatus(document.getElementById("calibration-status"), `Ошибка: ${error.message}`, "err");
      }
    }

    async function saveSafetyBaseline() {
      const systemPrompt = getValue("safety-baseline").trim();
      const status = document.getElementById("agents-status");
      const button = document.getElementById("safety-baseline-save");
      if (systemPrompt.length < 100) {
        setStatus(status, "Базовый контур должен быть не короче 100 символов", "err");
        return;
      }
      if (!confirm("Сохранить и сразу применить новую версию базового контура ко всем агентам?")) return;

      button.disabled = true;
      try {
        const revision = await api("/api/agents/safety-baseline", {
          method: "PUT",
          body: JSON.stringify({ system_prompt: systemPrompt })
        });
        await loadAgents();
        setStatus(status, `Контур версии ${revision.version} опубликован`, "ok");
      } catch (error) {
        setStatus(status, `Ошибка: ${error.message}`, "err");
      } finally {
        button.disabled = false;
      }
    }

    async function restartGateway() {
      const status = document.getElementById("agents-status");
      const button = document.getElementById("gateway-restart");
      if (!confirm("Перезапустить AI Gateway? Текущий ответ или голосовой запрос может прерваться.")) return;

      button.disabled = true;
      setStatus(status, "Перезапускаем Gateway…", "warn");
      try {
        const result = await api("/api/system/gateway/restart", { method: "POST" });
        setStatus(
          status,
          result.active ? "Gateway перезапущен и работает" : "Команда выполнена, служба ещё запускается",
          result.active ? "ok" : "warn"
        );
      } catch (error) {
        setStatus(status, `Ошибка перезапуска: ${error.message}`, "err");
      } finally {
        button.disabled = false;
      }
    }

    async function publishAgentRevision(revisionId, version) {
      const agent = selectedAgent();
      if (!agent || !confirm(`Опубликовать версию ${version} агента «${agent.display_name}»? Новые диалоги начнут использовать её сразу.`)) return;
      try {
        await api(`/api/agents/${encodeURIComponent(agent.id)}/revisions/${revisionId}/publish`, { method: "POST" });
        await loadAgents();
      } catch (error) {
        setStatus(document.getElementById("agents-status"), `Ошибка: ${error.message}`, "err");
      }
    }

    function applySettings(data) {
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
      setValue("openai_api_key", "");
      setValue("speech_api_key", "");
      setValue("stt_api_key", "");
      setValue("tts_api_key", "");
      document.getElementById("clear_stt_api_key").checked = false;
      document.getElementById("clear_tts_api_key").checked = false;
      setValue("music_recognition_provider", data.music_recognition_provider || "disabled");
      setValue("acrcloud_host", data.acrcloud_host || "");
      setValue("music_recognition_timeout_seconds", data.music_recognition_timeout_seconds || 8);
      setValue("acrcloud_access_key", "");
      setValue("acrcloud_access_secret", "");
      const musicBadge = document.getElementById("music-provider-badge");
      musicBadge.querySelector("span").textContent = data.music_recognition_provider === "acrcloud" ? "ACRCloud" : "Выключено";
      musicBadge.querySelector("i").className = `signal-dot ${data.music_recognition_provider === "acrcloud" ? "cyan" : ""}`;
      const imageBadge = document.getElementById("image-provider-badge");
      imageBadge.querySelector("span").textContent = data.image_search_provider === "openverse" ? "Openverse" : "Выключено";
      imageBadge.querySelector("i").className = `signal-dot ${data.image_search_provider === "openverse" ? "cyan" : ""}`;
      const visionBadge = document.getElementById("vision-provider-badge");
      const visionEnabled = data.vision_provider === "openai_compatible";
      visionBadge.querySelector("span").textContent = visionEnabled ? "Включено" : "Выключено";
      visionBadge.querySelector("i").className = `signal-dot ${visionEnabled ? "cyan" : ""}`;

      summary.textContent = `env=${data.environment}, LLM=${data.openai_api_key_preview || "(empty)"}, STT=${data.stt_api_key_preview || data.speech_api_key_preview || "(fallback LLM)"}, TTS=${data.tts_api_key_preview || data.speech_api_key_preview || "(fallback LLM)"}, images=${data.image_search_provider || "disabled"}, vision=${data.vision_provider || "disabled"}, melody=${data.music_recognition_provider || "disabled"}`;
      document.getElementById("environment-label").textContent = data.environment;
      document.querySelector(".retention-ring").textContent = `${data.message_retention_days}d`;
    }

    function collectSettingsPayload() {
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

    function renderConfigurationChanges(changes) {
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

    async function previewSettingsChange() {
      const button = document.getElementById("save-btn");
      button.disabled = true;
      setSaveStatus("Проверяем конфигурацию…", "warn");
      try {
        const payload = collectSettingsPayload();
        const preview = await api("/api/settings/preview", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        if (!preview.changes.length) {
          setSaveStatus("Изменений нет", "ok");
          return;
        }
        pendingSettingsPayload = payload;
        renderConfigurationChanges(preview.changes);
        document.getElementById("config-preview-dialog").showModal();
        setSaveStatus(`Проверено изменений: ${preview.changes.length}`, "ok");
      } catch (error) {
        setSaveStatus(`Проверка не пройдена: ${error.message}`, "err");
      } finally {
        button.disabled = false;
      }
    }

    async function applyPendingSettings(event) {
      event.preventDefault();
      if (!pendingSettingsPayload) return;
      const button = document.getElementById("config-preview-apply");
      button.disabled = true;
      setSaveStatus("Сохраняем, перезапускаем Gateway и ждём health-check…", "warn");
      try {
        const data = await api("/api/settings", {
          method: "POST",
          body: JSON.stringify(pendingSettingsPayload)
        });
        pendingSettingsPayload = null;
        document.getElementById("config-preview-dialog").close();
        applySettings(data);
        await loadConfigurationRevisions();
        setSaveStatus("Применено: Gateway перезапущен и прошёл health-check", "ok");
      } catch (error) {
        setSaveStatus(`Изменения отклонены: ${error.message}`, "err");
      } finally {
        button.disabled = false;
      }
    }

    async function rollbackConfiguration(revision) {
      if (!confirm(`Вернуть конфигурацию ${revision.id}? Gateway будет перезапущен и проверен.`)) return;
      setSaveStatus("Восстанавливаем выбранную ревизию…", "warn");
      try {
        await api(`/api/settings/revisions/${encodeURIComponent(revision.id)}/rollback`, {
          method: "POST"
        });
        await loadSettings();
        await loadConfigurationRevisions();
        setSaveStatus("Ревизия восстановлена, Gateway прошёл health-check", "ok");
      } catch (error) {
        setSaveStatus(`Rollback не выполнен: ${error.message}`, "err");
      }
    }

    async function loadConfigurationRevisions() {
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
            action.onclick = () => rollbackConfiguration(revision);
            row.append(action);
          }
          list.append(row);
        }
      } catch (error) {
        list.textContent = `История недоступна: ${error.message}`;
      }
    }

    async function loadSettings() {
      const data = await api("/api/settings", { method: "GET" });
      applySettings(data);
      document.body.classList.add("authenticated");
      authCard.style.display = "none";
      if (data.must_change_password) {
        passwordCard.style.display = "block";
        mainNav.style.display = "none";
        hideAllScreens();
        setStatus(passwordStatus, "Требуется сменить пароль", "warn");
      } else {
        passwordCard.style.display = "none";
        mainNav.style.display = "flex";
        switchTab("settings");
        setSaveStatus("Настройки загружены", "ok");
      }
    }

    async function login() {
      const username = getValue("username").trim();
      const password = getValue("password");

      authStatus.textContent = "Проверка доступа...";
      try {
        await createBrowserSession(username, password);
        await loadSettings();
        authStatus.textContent = "";
      } catch (error) {
        document.body.classList.remove("authenticated");
        authStatus.textContent = `Ошибка авторизации: ${error.message}`;
      }
    }

    const safetyPolicyScreen = createSafetyPolicyScreen({
      openAgents: () => switchTab("agents")
    });
    let qualityScreen;
    const historyScreen = createHistoryScreen({
      onFeedback: message => qualityScreen.openFeedback(message),
      onPeriodChange: () => qualityScreen.loadSummary()
    });
    qualityScreen = createQualityScreen({
      reloadHistory: () => historyScreen.load()
    });
    const memoryScreen = createMemoryScreen();
    const activityScreen = createActivityScreen({
      openMemory: proposal => {
        memoryScreen.prefillLearningOutcome(proposal);
        switchTab("memory");
      }
    });
    const infrastructureScreen = createInfrastructureScreen();
    navigate = createNavigation(tab => {
      clearInterval(infrastructureTimer);
      infrastructureTimer = null;
      clearInterval(calibrationTimer);
      calibrationTimer = null;
      if (tab === "settings") loadConfigurationRevisions();
      if (tab === "agents") loadAgents();
      if (tab === "studio") {
        loadStudio();
        qualityScreen.loadCases();
        activityScreen.load();
        loadCalibrationStatus();
        loadSpeechRuntimeSettings();
        calibrationTimer = setInterval(loadCalibrationStatus, 5000);
      }
      if (tab === "safety") safetyPolicyScreen.load();
      if (tab === "memory") memoryScreen.load();
      if (tab === "infrastructure") {
        infrastructureScreen.load();
        infrastructureTimer = setInterval(infrastructureScreen.load, 15000);
      }
      if (tab === "history") {
        historyScreen.load(true);
        qualityScreen.loadSummary();
      }
    });

    document.getElementById("login-btn").onclick = login;
    for (const id of ["username", "password"]) {
      document.getElementById(id).addEventListener("keydown", event => {
        if (event.key === "Enter") login();
      });
    }

    document.getElementById("logout-btn").onclick = async () => {
      try {
        await deleteBrowserSession();
      } catch (_) {
        // Локальное состояние всё равно сбрасывается.
      }
      clearInterval(infrastructureTimer);
      infrastructureTimer = null;
      clearInterval(calibrationTimer);
      calibrationTimer = null;
      setValue("password", "");
      document.body.classList.remove("authenticated");
      authCard.style.display = "block";
      authStatus.textContent = "";
    };

    document.getElementById("child-ui-link").href = `${location.protocol}//${location.hostname}:8000`;

    document.getElementById("reload-btn").onclick = async () => {
      try {
        await loadSettings();
      } catch (error) {
        setSaveStatus(`Ошибка: ${error.message}`, "err");
      }
    };

    document.getElementById("settings-tab").onclick = () => switchTab("settings");
    document.getElementById("agents-tab").onclick = () => switchTab("agents");
    document.getElementById("studio-tab").onclick = () => switchTab("studio");
    document.getElementById("safety-tab").onclick = () => switchTab("safety");
    document.getElementById("memory-tab").onclick = () => switchTab("memory");
    document.getElementById("infrastructure-tab").onclick = () => switchTab("infrastructure");
    document.getElementById("history-tab").onclick = () => switchTab("history");
    document.getElementById("safety-baseline-save").onclick = saveSafetyBaseline;
    document.getElementById("gateway-restart").onclick = restartGateway;
    document.getElementById("studio-agent").onchange = syncStudioVoice;
    document.getElementById("studio-voice-preset").onchange = event => {
      if (event.target.value) setValue("studio-speech-text", event.target.value);
    };
    document.getElementById("studio-run").onclick = runStudioTest;
    document.getElementById("studio-speak").onclick = speakStudioText;
    document.getElementById("calibration-start").onclick = startCalibration;
    document.getElementById("calibration-cancel").onclick = cancelCalibration;
    document.getElementById("speech-runtime-apply").onclick = applySpeechRuntimeSettings;
    document.getElementById("config-revisions-reload").onclick = loadConfigurationRevisions;
    document.getElementById("config-preview-apply").onclick = applyPendingSettings;
    document.getElementById("agent-save").onclick = async () => {
      const agent = selectedAgent();
      if (!agent) return;
      const payload = {
        display_name: getValue("agent-name").trim(),
        description: getValue("agent-description").trim(),
        icon: getValue("agent-icon").trim(),
        color: getValue("agent-color").trim(),
        greeting: getValue("agent-greeting").trim(),
        tts_voice: getValue("agent-voice") || null,
        tools: [
          ...(document.getElementById("agent-tool-music").checked ? ["music_recognition"] : []),
          ...(document.getElementById("agent-tool-web-search").checked ? ["web_search"] : []),
          ...(document.getElementById("agent-tool-image-search").checked ? ["image_search"] : []),
          ...(document.getElementById("agent-tool-image-understanding").checked ? ["image_understanding"] : [])
        ],
        permissions: document.getElementById("agent-permission-outdoor").checked ? ["supervised_outdoor_safety"] : [],
        enabled: getValue("agent-enabled") === "true",
        sort_order: Number(getValue("agent-order"))
      };
      try {
        await api(`/api/agents/${encodeURIComponent(agent.id)}`, {
          method: "PATCH",
          body: JSON.stringify(payload)
        });
        await loadAgents();
        setStatus(document.getElementById("agents-status"), "Карточка сохранена", "ok");
      } catch (error) {
        setStatus(document.getElementById("agents-status"), `Ошибка: ${error.message}`, "err");
      }
    };
    document.getElementById("agent-create-revision").onclick = async () => {
      const agent = selectedAgent();
      const systemPrompt = getValue("agent-new-prompt").trim();
      if (!agent) return;
      if (systemPrompt.length < 40) {
        setStatus(document.getElementById("agents-status"), "Промпт должен быть не короче 40 символов", "err");
        return;
      }
      try {
        await api(`/api/agents/${encodeURIComponent(agent.id)}/revisions`, {
          method: "POST",
          body: JSON.stringify({ system_prompt: systemPrompt })
        });
        await loadAgents();
        setStatus(document.getElementById("agents-status"), "Новая версия создана. Опубликуй её после проверки.", "ok");
      } catch (error) {
        setStatus(document.getElementById("agents-status"), `Ошибка: ${error.message}`, "err");
      }
    };
    document.getElementById("tts_voice").onchange = () => {
      const customInput = document.getElementById("tts_voice_custom");
      const customField = document.getElementById("tts_voice_custom_field");
      customField.hidden = getValue("tts_voice") !== "__custom__";
      if (!customField.hidden) {
        customInput.focus();
      }
    };

    document.getElementById("change-password-btn").onclick = async () => {
      const password = getValue("new_admin_password");
      const confirm = getValue("new_admin_password_confirm");

      if (password.length < 8) {
        setStatus(passwordStatus, "Минимум 8 символов", "err");
        return;
      }
      if (password !== confirm) {
        setStatus(passwordStatus, "Пароли не совпадают", "err");
        return;
      }

      try {
        await api("/api/change-password", {
          method: "POST",
          body: JSON.stringify({ new_password: password })
        });

        setValue("password", password);
        setValue("new_admin_password", "");
        setValue("new_admin_password_confirm", "");
        setStatus(passwordStatus, "Пароль изменён", "ok");
        await createBrowserSession(getValue("username").trim(), password);
        await loadSettings();
      } catch (error) {
        setStatus(passwordStatus, `Ошибка смены пароля: ${error.message}`, "err");
      }
    };

    document.getElementById("save-btn").onclick = previewSettingsChange;

    async function restoreBrowserSession() {
      try {
        await loadSettings();
      } catch (_) {
        // Нет действующей cookie-сессии: остаёмся на форме входа.
      }
    }

    restoreBrowserSession();
