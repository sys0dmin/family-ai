import { api } from "./api-client.js?v=admin-modules-2";
import { formatDateTime, getValue, setStatus, setValue } from "./dom.js?v=admin-modules-3";

export function createAgentsScreen() {
  let agents = [];
  let selectedAgentId = null;

  function selected() {
    return agents.find(agent => agent.id === selectedAgentId) || null;
  }

  function renderList() {
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
        renderList();
        renderEditor();
      };
      list.append(button);
    }
  }

  function renderEditor() {
    const agent = selected();
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
    for (const [id, tool] of [
      ["agent-tool-music", "music_recognition"],
      ["agent-tool-web-search", "web_search"],
      ["agent-tool-image-search", "image_search"],
      ["agent-tool-image-understanding", "image_understanding"]
    ]) document.getElementById(id).checked = (agent.tools || []).includes(tool);
    document.getElementById("agent-permission-outdoor").checked =
      (agent.permissions || []).includes("supervised_outdoor_safety");
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
      action.onclick = () => publishRevision(revision.id, revision.version);
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

  async function load() {
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
      renderList();
      renderEditor();
      setStatus(status, "Обновлено", "ok");
      return agents;
    } catch (error) {
      setStatus(status, `Ошибка: ${error.message}`, "err");
      throw error;
    }
  }

  async function saveBaseline() {
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
      await load();
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

  async function publishRevision(revisionId, version) {
    const agent = selected();
    if (!agent || !confirm(`Опубликовать версию ${version} агента «${agent.display_name}»? Новые диалоги начнут использовать её сразу.`)) return;
    try {
      await api(`/api/agents/${encodeURIComponent(agent.id)}/revisions/${revisionId}/publish`, { method: "POST" });
      await load();
    } catch (error) {
      setStatus(document.getElementById("agents-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  async function saveCard() {
    const agent = selected();
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
      permissions: document.getElementById("agent-permission-outdoor").checked
        ? ["supervised_outdoor_safety"] : [],
      enabled: getValue("agent-enabled") === "true",
      sort_order: Number(getValue("agent-order"))
    };
    try {
      await api(`/api/agents/${encodeURIComponent(agent.id)}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      await load();
      setStatus(document.getElementById("agents-status"), "Карточка сохранена", "ok");
    } catch (error) {
      setStatus(document.getElementById("agents-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  async function createRevision() {
    const agent = selected();
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
      await load();
      setStatus(document.getElementById("agents-status"), "Новая версия создана. Опубликуй её после проверки.", "ok");
    } catch (error) {
      setStatus(document.getElementById("agents-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  document.getElementById("safety-baseline-save").onclick = saveBaseline;
  document.getElementById("gateway-restart").onclick = restartGateway;
  document.getElementById("agent-save").onclick = saveCard;
  document.getElementById("agent-create-revision").onclick = createRevision;

  return {
    enabled: () => agents.filter(agent => agent.enabled),
    load
  };
}
