/* Stable synthetic data for Admin UI screenshot regression tests. */

const copy = {
  settings: ["Настройки", "System configuration"],
  agents: ["Агенты", "Agent studio"],
  studio: ["Тест-студия", "Prompt & voice laboratory"],
  infrastructure: ["Инфраструктура", "Project operations"],
};

function setValue(id, value) {
  const element = document.getElementById(id);
  if (element) element.value = value;
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function activateScreen(screen) {
  document.body.classList.add("authenticated");
  document.querySelectorAll(".tab-button").forEach((button) => {
    const active = button.id === `${screen}-tab`;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  for (const id of [
    "settings-card",
    "agents-card",
    "studio-card",
    "safety-policy-card",
    "memory-card",
    "infrastructure-card",
    "history-card",
  ]) {
    const element = document.getElementById(id);
    if (element) element.style.display = id === `${screen}-card` ? "block" : "none";
  }
  document.getElementById("page-title").textContent = copy[screen][0];
  document.getElementById("page-kicker").textContent = copy[screen][1];
  document.getElementById("environment-label").textContent = "visual fixture";
}

function fillSettings() {
  setValue("openai_model", "family-ai-test-model");
  setValue("openai_base_url", "https://provider.invalid/v1");
  setValue("speech_base_url", "http://speech.test:8010/v1");
  setValue("stt_model", "whisper-small");
  setValue("tts_model", "silero_ru");
  setValue("stt_initial_prompt", "Лера, Мурка, Байтик, Нотка");
  setValue("voice_max_in_flight", "2");
  setValue("voice_stt_timeout_seconds", "35");
  setValue("voice_llm_timeout_seconds", "20");
  setValue("voice_tts_timeout_seconds", "30");
  setValue("message_retention_days", "10");
  setValue("vision_model", "vision-test-model");
  setValue("vision_base_url", "https://vision.invalid/v1");
  setValue("vision_max_image_mb", "10");
  setValue("acrcloud_host", "identify.example.invalid");
  document.getElementById("summary").textContent = "Синтетическая конфигурация";
  document.getElementById("config-revision-list").innerHTML = `
    <div class="config-revision active"><div class="config-revision-copy">
      <strong>apply · 20260815T120000-abcdef <span class="config-revision-badge">active</span></strong>
      <small>15.08.2026, 12:00 · admin · 123456789abc · изменений 2</small>
    </div></div>`;
}

function showConfigurationPreview() {
  document.getElementById("config-preview-list").innerHTML = `
    <div class="config-change"><strong>openai model</strong><span>model-a</span><i>→</i><span>model-b</span></div>
    <div class="config-change"><strong>openai api key</strong><span>настроен</span><i>→</i><span>настроен</span></div>
    <div class="config-change"><strong>message retention days</strong><span>10</span><i>→</i><span>14</span></div>`;
  document.getElementById("config-preview-dialog").showModal();
}

function agentButton(icon, name, active = false) {
  return `<button class="agent-list-button${active ? " active" : ""}">
    <span class="agent-icon">${icon}</span><span><strong>${name}</strong>
    <div class="muted">Доступен</div></span></button>`;
}

function fillAgents() {
  document.getElementById("agent-list").innerHTML = [
    agentButton("🐻", "Учитель-друг", true),
    agentButton("🐱", "Мурка"),
    agentButton("🦝", "Байтик"),
    agentButton("🚀", "Алиса Селезнёва"),
  ].join("");
  document.getElementById("agent-editor").style.display = "block";
  setValue("agent-name", "Учитель-друг");
  setValue("agent-icon", "🐻");
  setValue("agent-color", "blue");
  setValue("agent-order", "10");
  setValue("agent-description", "Добрый друг и понятный учитель для Леры.");
  setValue("agent-greeting", "Привет! Что интересного узнаем сегодня?");
  setValue("agent-new-prompt", "Стабильный синтетический prompt для визуальной проверки.");
  document.getElementById("agent-revisions").innerHTML = `
    <div class="revision active"><div class="revision-head">
      <strong>Версия 7 · опубликована</strong><button class="secondary" disabled>Активна</button>
    </div><div class="muted">02.08.2026, 12:00 · visual-test</div>
    <div class="revision-prompt">Безопасный тестовый текст без данных ребёнка.</div></div>`;
}

function fillStudio() {
  document.getElementById("studio-agent").innerHTML =
    '<option value="teacher_friend">🐻 Учитель-друг</option>';
  setValue("studio-prompt", "Расскажи один короткий интересный факт о космосе.");
  setValue("studio-speech-text", "У Сатурна есть красивые кольца из льда и камней.");
  document.getElementById("studio-raw").textContent =
    "У Сатурна есть кольца из миллиардов кусочков льда и камня.";
  document.getElementById("studio-final").textContent =
    "У Сатурна есть красивые кольца из льда и камней.";
  document.getElementById("studio-safety").textContent = "Safety passed";
  document.getElementById("studio-timing").textContent = "LLM 820 мс";
  document.getElementById("regression-list").innerHTML = `
    <article class="regression-case"><div class="regression-case-head">
      <div><strong>Космос · короткий факт</strong><div class="muted">Подтверждено родителем</div></div>
      <button class="secondary">Запустить</button></div>
      <div class="regression-prompt">Расскажи интересный факт о Сатурне.</div>
    </article>`;
  document.getElementById("regression-status").textContent = "1 проверка";
}

function fillInfrastructure() {
  setText("infrastructure-title", "Инфраструктура требует внимания");
  setText("infrastructure-subtitle", "Один ресурс близок к пределу");
  setText("infrastructure-orb-label", "Degraded");
  document.getElementById("infrastructure-orb").className = "health-orb degraded";
  const count = document.getElementById("operational-alert-count");
  count.className = "health-pill degraded";
  count.textContent = "1 активно";
  document.getElementById("operational-alert-list").innerHTML = `
    <article class="operational-alert warning">
      <div class="operational-alert-copy"><div class="operational-alert-heading">
        <span class="operational-severity warning">Внимание</span>
        <strong>Мало места на family-ai-speech</strong></div>
        <p>Текущее значение: 14% свободно; порог: 15.</p>
        <span class="operational-alert-meta">speech · с 02.08.2026, 12:00</span>
      </div><button class="secondary operational-ack">Вижу</button>
    </article>`;
  setText(
    "operational-thresholds",
    "Пороги: диск ≤ 15% / 8% свободно · очередь Speech ≥ 2 / 4 · ошибки подряд ≥ 3 / 5 · история 30 дней",
  );
  for (const nodeId of ["gateway", "database", "speech"]) {
    const card = document.getElementById(`server-${nodeId}`);
    const pill = card.querySelector('[data-field="status"]');
    pill.className = `health-pill${nodeId === "speech" ? " degraded" : ""}`;
    pill.textContent = nodeId === "speech" ? "Degraded" : "Healthy";
    card.querySelector('[data-field="uptime"]').textContent = "12 д 4 ч";
    card.querySelector('[data-field="load"]').textContent = nodeId === "speech" ? "2.81" : "0.42";
    card.querySelector('[data-field="cores"]').textContent = "4";
    card.querySelector('[data-field="cpu-value"]').textContent = nodeId === "speech" ? "82.0%" : "18.0%";
    card.querySelector('[data-field="memory-value"]').textContent = "55.0% · 4.4 GB / 8 GB";
    card.querySelector('[data-field="disk-value"]').textContent = nodeId === "speech" ? "86.0% · 86 GB / 100 GB" : "41.0% · 41 GB / 100 GB";
  }
  setText("database-version", "PostgreSQL 16.4");
  setText("database-status", "Healthy");
  setText("database-latency", "1.8 ms");
  setText("database-uptime", "12 д 4 ч");
  setText("database-size", "248 MB");
  setText("database-connections", "8 / 100");
  setText("pipeline-health", "Live");
  setText("pipeline-recording", "3.1 с");
  setText("pipeline-stt", "7.8 с");
  setText("pipeline-vision", "—");
  setText("pipeline-llm", "1.7 с");
  setText("pipeline-tts", "9.4 с");
  setText("pipeline-first-ready", "3.2 с");
  setText("pipeline-first-playback", "3.4 с");
  setText("pipeline-total", "22.0 с");
  setText("speech-queue", "2");
  setText("speech-active", "tts");
  setText("pipeline-errors", "1");
  setText("pipeline-cancellations", "0");
  setText("pipeline-chunks", "3");
  setText("pipeline-confidence", "91%");
  setText("infrastructure-checked", "Последняя проверка: 02.08.2026, 12:00");
}

activateScreen(window.__VISUAL_SCREEN__);
fillSettings();
fillAgents();
fillStudio();
fillInfrastructure();
if (window.__VISUAL_DIALOG__) showConfigurationPreview();
document.documentElement.dataset.visualOverflow = String(
  document.documentElement.scrollWidth > window.innerWidth,
);
