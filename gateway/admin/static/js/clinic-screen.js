import { api } from "./api-client.js?v=admin-modules-2";
import { byId, formatDateTime, setStatus } from "./dom.js?v=admin-modules-2";

const statusLabels = {
  active: "Идёт",
  paused: "Пауза",
  completed: "Завершено",
  left: "Карточка закрыта"
};

export function createClinicScreen() {
  let catalog = [];

  function renderPreview() {
    const selected = catalog.find(item => item.id === byId("clinic-preview-select").value);
    const container = byId("clinic-preview");
    container.replaceChildren();
    if (!selected) return;

    const heading = document.createElement("div");
    heading.className = "clinic-preview-head";
    const icon = document.createElement("span");
    icon.textContent = selected.patient_icon;
    const title = document.createElement("div");
    const strong = document.createElement("strong");
    strong.textContent = selected.title;
    const small = document.createElement("small");
    small.textContent = `${selected.patient_name} · версия ${selected.version}`;
    title.append(strong, small);
    heading.append(icon, title);

    const context = document.createElement("div");
    context.className = "clinic-preview-context";
    const mood = document.createElement("span");
    mood.textContent = `Настроение: ${selected.mood || "спокойное"}`;
    const complaint = document.createElement("span");
    complaint.textContent = `Жалоба: ${selected.complaint || "Хочет, чтобы о нём позаботились."}`;
    context.append(mood, complaint);

    const monitor = document.createElement("div");
    monitor.className = "clinic-monitor-preview";
    for (const vital of selected.vitals) {
      const item = document.createElement("div");
      const label = document.createElement("span");
      label.textContent = `${vital.icon} ${vital.label}`;
      const value = document.createElement("strong");
      value.textContent = `${vital.value} ${vital.unit}`.trim();
      item.append(label, value);
      monitor.append(item);
    }

    const actions = document.createElement("div");
    actions.className = "clinic-action-preview";
    for (const action of selected.actions) {
      const item = document.createElement("div");
      const label = document.createElement("strong");
      label.textContent = `${action.icon} ${action.label}`;
      const response = document.createElement("small");
      response.textContent = action.response;
      item.append(label, response);
      actions.append(item);
    }

    const safety = document.createElement("div");
    safety.className = "clinic-safety-note";
    safety.textContent = "Игровые показатели. Реальная жалоба ставит игру на паузу и зовёт взрослого.";
    container.append(heading, context, monitor, actions, safety);
  }

  async function operate(session, operation) {
    const label = operation === "reset" ? "сбросить" : operation === "pause" ? "поставить на паузу" : "продолжить";
    if (!confirm(`Точно ${label} карточку «${session.title}»?`)) return;
    if (operation === "reset") {
      await api(`/api/clinic/sessions/${session.id}`, { method: "DELETE" });
    } else {
      await api(`/api/clinic/sessions/${session.id}/${operation}`, { method: "POST" });
    }
    await loadSessions();
  }

  function renderSessions(data) {
    const container = byId("clinic-session-list");
    container.replaceChildren();
    if (!data.items.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Карточек пациентов пока нет";
      container.append(empty);
      return;
    }
    for (const session of data.items) {
      const card = document.createElement("article");
      card.className = "clinic-session-card";
      const head = document.createElement("div");
      head.className = "clinic-session-head";
      const summary = document.createElement("div");
      const icon = document.createElement("span");
      icon.textContent = session.patient_icon;
      const text = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = session.patient_name;
      const meta = document.createElement("small");
      meta.textContent = `${statusLabels[session.status] || session.status} · ${formatDateTime(session.updated_at)}`;
      text.append(title, meta);
      summary.append(icon, text);
      const controls = document.createElement("div");
      controls.className = "row card-actions";
      if (session.status === "active" || session.status === "paused") {
        const toggle = document.createElement("button");
        toggle.className = "secondary";
        toggle.textContent = session.status === "paused" ? "Продолжить" : "Пауза";
        toggle.onclick = () => operate(session, session.status === "paused" ? "resume" : "pause");
        controls.append(toggle);
      }
      const reset = document.createElement("button");
      reset.className = "danger";
      reset.textContent = "Сбросить";
      reset.onclick = () => operate(session, "reset");
      controls.append(reset);
      head.append(summary, controls);
      card.append(head);
      container.append(card);
    }
  }

  async function loadCatalog() {
    const data = await api("/api/clinic/catalog", { method: "GET" });
    catalog = data.items;
    const select = byId("clinic-preview-select");
    const previous = select.value;
    select.replaceChildren();
    for (const item of catalog) {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = `${item.patient_icon} ${item.title}`;
      select.append(option);
    }
    if (catalog.some(item => item.id === previous)) select.value = previous;
    renderPreview();
  }

  async function loadSessions() {
    const data = await api("/api/clinic/sessions", { method: "GET" });
    renderSessions(data);
  }

  async function load() {
    setStatus(byId("clinic-studio-status"), "Загрузка…", "warn");
    try {
      await Promise.all([loadCatalog(), loadSessions()]);
      setStatus(byId("clinic-studio-status"), "Готово", "ok");
    } catch (error) {
      setStatus(byId("clinic-studio-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  byId("clinic-preview-select").onchange = renderPreview;
  byId("clinic-studio-refresh").onclick = load;
  return { load };
}
