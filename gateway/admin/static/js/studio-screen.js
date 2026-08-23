import { api, requestBlob } from "./api-client.js?v=admin-modules-2";
import { getValue, setStatus, setValue } from "./dom.js?v=admin-modules-3";

const KNOWN_VOICES = new Set([
  "xenia", "baya", "kseniya", "aidar", "eugene",
  "lulwa", "noura", "aisha", "abdullah", "fahad", "sultan"
]);

export function createStudioScreen(agentsScreen) {
  function populateAgents() {
    const select = document.getElementById("studio-agent");
    const previous = select.value;
    select.replaceChildren();
    for (const agent of agentsScreen.enabled()) {
      const option = document.createElement("option");
      option.value = agent.id;
      option.textContent = `${agent.icon} ${agent.display_name}`;
      select.append(option);
    }
    if ([...select.options].some(option => option.value === previous)) select.value = previous;
    syncVoice();
  }

  function syncVoice() {
    const agent = agentsScreen.enabled().find(item => item.id === getValue("studio-agent"));
    if (agent?.tts_voice && KNOWN_VOICES.has(agent.tts_voice)) {
      setValue("studio-voice", agent.tts_voice);
    }
  }

  async function load() {
    if (!agentsScreen.enabled().length) await agentsScreen.load();
    populateAgents();
  }

  async function runTest() {
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

  async function speak() {
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

  document.getElementById("studio-agent").onchange = syncVoice;
  document.getElementById("studio-voice-preset").onchange = event => {
    if (event.target.value) setValue("studio-speech-text", event.target.value);
  };
  document.getElementById("studio-run").onclick = runTest;
  document.getElementById("studio-speak").onclick = speak;

  return { load, populateAgents };
}
