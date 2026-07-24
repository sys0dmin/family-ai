import { api } from "./api-client.js";
import { byId, formatDateTime, setStatus } from "./dom.js";

export function createInfrastructureScreen() {
  const history = { gateway: [], database: [], speech: [] };

  function formatBytes(value) {
    if (value == null) return "—";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = Number(value);
    let unit = 0;
    while (size >= 1024 && unit < units.length - 1) {
      size /= 1024;
      unit += 1;
    }
    return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
  }

  function formatDuration(seconds) {
    if (seconds == null) return "—";
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor(seconds % 86400 / 3600);
    const minutes = Math.floor(seconds % 3600 / 60);
    if (days) return `${days} д ${hours} ч`;
    if (hours) return `${hours} ч ${minutes} мин`;
    return `${minutes} мин`;
  }

  function healthLabel(status) {
    return {
      healthy: "Healthy",
      degraded: "Degraded",
      down: "Down",
      unconfigured: "No metrics"
    }[status] || status;
  }

  function setHealthPill(element, status) {
    element.className = `health-pill ${status}`;
    element.textContent = healthLabel(status);
  }

  function setResource(card, name, usage, directPercent = null) {
    const percent = directPercent ?? usage?.percent;
    const value = card.querySelector(`[data-field="${name}-value"]`);
    const bar = card.querySelector(`[data-field="${name}-bar"]`);
    if (percent == null) {
      value.textContent = "—";
      bar.style.width = "0";
      return;
    }
    value.textContent = usage
      ? `${percent.toFixed(1)}% · ${formatBytes(usage.used_bytes)} / ${formatBytes(usage.total_bytes)}`
      : `${percent.toFixed(1)}%`;
    bar.style.width = `${Math.min(100, Math.max(0, percent))}%`;
    bar.classList.toggle("warning", percent >= 90);
  }

  function renderSparkline(nodeId, cpuPercent, path) {
    if (cpuPercent != null) {
      history[nodeId].push(cpuPercent);
      history[nodeId] = history[nodeId].slice(-24);
    }
    const values = history[nodeId];
    if (!values.length) {
      path.setAttribute("d", "");
      return;
    }
    const plotted = values.length === 1 ? [values[0], values[0]] : values;
    const points = plotted.map((value, index) => {
      const x = index / (plotted.length - 1) * 300;
      const y = 48 - Math.min(100, Math.max(0, value)) / 100 * 42;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    path.setAttribute("d", `M ${points.join(" L ")}`);
  }

  function renderNode(node) {
    const card = byId(`server-${node.id}`);
    if (!card) return;
    setHealthPill(card.querySelector('[data-field="status"]'), node.status);
    card.querySelector('[data-field="uptime"]').textContent =
      formatDuration(node.uptime_seconds);
    card.querySelector('[data-field="load"]').textContent =
      node.load1 == null ? "—" : node.load1.toFixed(2);
    card.querySelector('[data-field="cores"]').textContent = node.cpu_cores ?? "—";
    setResource(card, "cpu", null, node.cpu_percent);
    setResource(card, "memory", node.memory);
    setResource(card, "disk", node.disk);
    renderSparkline(
      node.id,
      node.cpu_percent,
      card.querySelector('[data-field="sparkline"]')
    );
  }

  function render(data) {
    const statusCopy = {
      healthy: ["Вся инфраструктура в норме", "Все компоненты отвечают штатно"],
      degraded: ["Инфраструктура требует внимания", "Один из ресурсов близок к пределу"],
      down: ["Есть недоступный компонент", "Проверьте состояние сервисов и сети"],
      unconfigured: ["Сбор метрик не настроен", "Укажите endpoints node exporter"]
    };
    byId("infrastructure-title").textContent = statusCopy[data.status][0];
    byId("infrastructure-subtitle").textContent = statusCopy[data.status][1];
    byId("infrastructure-orb").className = `health-orb ${data.status}`;
    byId("infrastructure-orb-label").textContent = healthLabel(data.status);
    for (const node of data.nodes) renderNode(node);
    const database = data.database;
    setHealthPill(byId("database-status"), database.status);
    byId("database-version").textContent = database.version || "PostgreSQL";
    byId("database-latency").textContent =
      database.latency_ms == null ? "—" : `${database.latency_ms.toFixed(1)} ms`;
    byId("database-uptime").textContent = formatDuration(database.uptime_seconds);
    byId("database-size").textContent = formatBytes(database.size_bytes);
    byId("database-connections").textContent =
      database.connections == null
        ? "—"
        : `${database.connections} / ${database.max_connections}`;
    byId("infrastructure-checked").textContent =
      `Последняя проверка: ${formatDateTime(data.checked_at)}`;
  }

  function formatPipelineMs(value) {
    if (value == null) return "—";
    return value >= 1000 ? `${(value / 1000).toFixed(1)} с` : `${value} мс`;
  }

  async function loadVoiceObservability() {
    const data = await api("/api/voice-observability", { method: "GET" });
    const gateway = data.gateway.data;
    const speech = data.speech.data;
    const healthy =
      data.gateway.status === "healthy" && data.speech.status === "healthy";
    byId("pipeline-health").textContent = healthy ? "Live" : "Недоступно";
    const stages = gateway?.stages || {};
    byId("pipeline-recording").textContent = formatPipelineMs(
      stages.recording?.last_ms
    );
    byId("pipeline-stt").textContent = formatPipelineMs(stages.stt?.last_ms);
    byId("pipeline-llm").textContent = formatPipelineMs(stages.llm?.last_ms);
    byId("pipeline-tts").textContent = formatPipelineMs(stages.tts?.last_ms);
    byId("pipeline-total").textContent = formatPipelineMs(stages.total?.last_ms);
    byId("speech-queue").textContent = speech?.queue_depth ?? "—";
    byId("speech-active").textContent = speech?.active_stage || "свободен";
    byId("pipeline-errors").textContent = gateway?.errors ?? "—";
    const recent = gateway?.recent || [];
    const confidence = recent.length
      ? recent[recent.length - 1].stt_confidence
      : null;
    byId("pipeline-confidence").textContent =
      confidence == null ? "—" : `${Math.round(confidence * 100)}%`;
  }

  async function load() {
    const status = byId("infrastructure-status");
    setStatus(status, "Собираем метрики…", "warn");
    try {
      const data = await api("/api/infrastructure", { method: "GET" });
      render(data);
      try {
        await loadVoiceObservability();
      } catch (_) {
        byId("pipeline-health").textContent = "Недоступно";
      }
      setStatus(
        status,
        "Live · 15 sec",
        data.status === "healthy" ? "ok" : "warn"
      );
    } catch (error) {
      setStatus(status, `Ошибка: ${error.message}`, "err");
      byId("infrastructure-title").textContent = "Не удалось получить снимок";
    }
  }

  byId("infrastructure-refresh").onclick = load;
  return { load };
}
