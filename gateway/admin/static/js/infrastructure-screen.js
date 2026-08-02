import { api } from "./api-client.js";
import { byId, formatDateTime, setStatus } from "./dom.js";

export function createInfrastructureScreen() {
  const history = { gateway: [], database: [], speech: [] };
  let loading = false;

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

  function renderVoiceObservability(data) {
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
    byId("pipeline-vision").textContent = formatPipelineMs(
      stages.vision?.last_ms
    );
    byId("pipeline-llm").textContent = formatPipelineMs(stages.llm?.last_ms);
    byId("pipeline-tts").textContent = formatPipelineMs(stages.tts?.last_ms);
    byId("pipeline-first-ready").textContent = formatPipelineMs(
      stages.first_audio_ready?.last_ms
    );
    byId("pipeline-first-playback").textContent = formatPipelineMs(
      stages.client_first_playback?.last_ms
    );
    byId("pipeline-total").textContent = formatPipelineMs(stages.total?.last_ms);
    byId("speech-queue").textContent = speech?.queue_depth ?? "—";
    byId("speech-active").textContent = speech?.active_stage || "свободен";
    byId("pipeline-errors").textContent = gateway?.errors ?? "—";
    byId("pipeline-cancellations").textContent =
      gateway?.cancellations ?? "—";
    const recent = gateway?.recent || [];
    const latest = recent.length ? recent[recent.length - 1] : null;
    byId("pipeline-chunks").textContent = latest?.chunk_count ?? "—";
    const confidence = recent.length
      ? latest.stt_confidence
      : null;
    byId("pipeline-confidence").textContent =
      confidence == null ? "—" : `${Math.round(confidence * 100)}%`;
  }

  function alertTime(alert) {
    const start = formatDateTime(alert.first_seen_at);
    return alert.resolved_at
      ? `${start} → ${formatDateTime(alert.resolved_at)}`
      : `с ${start}`;
  }

  function createAlertCard(alert, active) {
    const card = document.createElement("article");
    card.className = `operational-alert ${alert.severity}${alert.acknowledged_at ? " acknowledged" : ""}`;

    const copy = document.createElement("div");
    copy.className = "operational-alert-copy";
    const heading = document.createElement("div");
    heading.className = "operational-alert-heading";
    const severity = document.createElement("span");
    severity.className = `operational-severity ${alert.severity}`;
    severity.textContent = alert.severity === "critical" ? "Критично" : "Внимание";
    const title = document.createElement("strong");
    title.textContent = alert.title;
    heading.append(severity, title);
    const detail = document.createElement("p");
    detail.textContent = alert.detail;
    const meta = document.createElement("span");
    meta.className = "operational-alert-meta";
    meta.textContent = `${alert.scope} · ${alertTime(alert)}`;
    copy.append(heading, detail, meta);
    card.append(copy);

    if (active) {
      const action = document.createElement("button");
      action.className = "secondary operational-ack";
      action.textContent = alert.acknowledged_at ? "✓ Подтверждено" : "Вижу";
      action.disabled = Boolean(alert.acknowledged_at);
      action.onclick = async () => {
        action.disabled = true;
        try {
          await api(`/api/infrastructure/alerts/${alert.id}/acknowledge`, {
            method: "POST"
          });
          await load();
        } catch (error) {
          action.disabled = false;
          setStatus(byId("infrastructure-status"), `Ошибка: ${error.message}`, "err");
        }
      };
      card.append(action);
    }
    return card;
  }

  function renderAlerts(alerts, infrastructureStatus) {
    const active = alerts.active || [];
    const historyItems = alerts.history || [];
    const count = byId("operational-alert-count");
    count.className = `health-pill ${active.some(item => item.severity === "critical") ? "down" : active.length ? "degraded" : ""}`;
    count.textContent = active.length ? `${active.length} активно` : "Всё спокойно";
    const hasCritical = active.some(item => item.severity === "critical");
    const statusPriority = { healthy: 0, unconfigured: 1, degraded: 2, down: 3 };
    const alertStatus = hasCritical ? "down" : active.length ? "degraded" : "healthy";
    const effectiveStatus = statusPriority[alertStatus] > statusPriority[infrastructureStatus]
      ? alertStatus
      : infrastructureStatus;
    if (effectiveStatus !== infrastructureStatus) {
      byId("infrastructure-orb").className = `health-orb ${effectiveStatus}`;
      byId("infrastructure-orb-label").textContent = healthLabel(effectiveStatus);
      byId("infrastructure-title").textContent = hasCritical
        ? "Инфраструктура требует вмешательства"
        : "Инфраструктура требует внимания";
      byId("infrastructure-subtitle").textContent = hasCritical
        ? "Есть активное критическое техническое событие"
        : "Один из технических сигналов достиг порога";
    }

    const list = byId("operational-alert-list");
    list.replaceChildren();
    if (!active.length) {
      const empty = document.createElement("div");
      empty.className = "operational-alert-empty";
      empty.textContent = "Пороговые значения в норме, сервисы отвечают.";
      list.append(empty);
    } else {
      active.forEach(alert => list.append(createAlertCard(alert, true)));
    }

    const thresholds = alerts.thresholds;
    byId("operational-thresholds").textContent = thresholds
      ? `Пороги: диск ≤ ${thresholds.disk_warning_free_percent}% / ${thresholds.disk_critical_free_percent}% свободно · очередь Speech ≥ ${thresholds.speech_queue_warning} / ${thresholds.speech_queue_critical} · ошибки подряд ≥ ${thresholds.voice_error_streak_warning} / ${thresholds.voice_error_streak_critical} · история ${thresholds.history_days} дней`
      : "";

    byId("operational-history-count").textContent = historyItems.length;
    const history = byId("operational-history-list");
    history.replaceChildren();
    if (!historyItems.length) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = "История пока пуста.";
      history.append(empty);
    } else {
      historyItems.forEach(alert => history.append(createAlertCard(alert, false)));
    }
  }

  async function load() {
    if (loading) return;
    loading = true;
    const status = byId("infrastructure-status");
    setStatus(status, "Собираем метрики…", "warn");
    try {
      const overview = await api("/api/infrastructure/scan", { method: "POST" });
      const data = overview.infrastructure;
      render(data);
      renderVoiceObservability(overview.voice);
      renderAlerts(overview.alerts, data.status);
      const hasAlerts = overview.alerts.active.length > 0;
      setStatus(
        status,
        "Live · 15 sec",
        data.status === "healthy" && !hasAlerts ? "ok" : "warn"
      );
    } catch (error) {
      setStatus(status, `Ошибка: ${error.message}`, "err");
      byId("infrastructure-title").textContent = "Не удалось получить снимок";
    } finally {
      loading = false;
    }
  }

  byId("infrastructure-refresh").onclick = load;
  return { load };
}
