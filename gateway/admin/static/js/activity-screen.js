import { api } from "./api-client.js?v=admin-modules-2";
import { byId, formatDateTime, setStatus } from "./dom.js?v=admin-modules-2";

const statusLabels = {
  active: "Идёт",
  completed: "Завершено",
  cancelled: "Остановлено",
  left: "Обычный разговор"
};

export function createActivityScreen({ openMemory }) {
  let catalog = [];

  function renderPreview() {
    const selected = catalog.find(item => item.id === byId("activity-preview-select").value);
    const container = byId("activity-preview");
    container.replaceChildren();
    if (!selected) return;
    const heading = document.createElement("div");
    heading.className = "activity-preview-head";
    heading.innerHTML = `<span style="--activity-color:${selected.color}">${selected.icon}</span><div><strong></strong><small></small></div>`;
    heading.querySelector("strong").textContent = selected.title;
    heading.querySelector("small").textContent = `${selected.agent_id} · ${selected.total_steps} шага`;
    const opening = document.createElement("p");
    opening.className = "activity-opening";
    opening.textContent = selected.opening_text;
    const steps = document.createElement("ol");
    steps.className = "activity-step-list";
    for (const step of selected.steps) {
      const item = document.createElement("li");
      item.innerHTML = `<span>${step.icon}</span><div><strong></strong><p></p></div>`;
      item.querySelector("strong").textContent = step.title;
      item.querySelector("p").textContent = step.instruction;
      steps.append(item);
    }
    const outcome = document.createElement("div");
    outcome.className = "activity-outcome";
    outcome.textContent = `Предложение родителю: ${selected.completion_summary}`;
    container.append(heading, opening, steps, outcome);
  }

  async function resetSession(session) {
    if (!confirm(`Сбросить состояние «${session.title}»? История сообщений останется.`)) return;
    await api(`/api/activities/sessions/${session.id}`, { method: "DELETE" });
    await loadSessions();
  }

  function renderSessions(data) {
    const container = byId("activity-session-list");
    container.replaceChildren();
    if (!data.items.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Сохранённых состояний пока нет";
      container.append(empty);
      return;
    }
    for (const session of data.items) {
      const card = document.createElement("article");
      card.className = "activity-session-card";
      const head = document.createElement("div");
      head.className = "activity-session-head";
      const title = document.createElement("div");
      title.innerHTML = `<span>${session.icon}</span><div><strong></strong><small></small></div>`;
      title.querySelector("strong").textContent = session.title;
      title.querySelector("small").textContent =
        `${statusLabels[session.status] || session.status} · шаг ${Math.min(session.current_step + 1, session.total_steps)} из ${session.total_steps} · ${formatDateTime(session.updated_at)}`;
      const actions = document.createElement("div");
      actions.className = "row card-actions";
      if (session.completion_summary) {
        const memory = document.createElement("button");
        memory.className = "primary";
        memory.textContent = "→ В Память";
        memory.onclick = () => openMemory({
          topic: session.title,
          summary: session.completion_summary
        });
        actions.append(memory);
      }
      const reset = document.createElement("button");
      reset.className = "secondary";
      reset.textContent = "Сбросить";
      reset.onclick = () => resetSession(session);
      actions.append(reset);
      head.append(title, actions);
      if (session.current_step_title) {
        const current = document.createElement("div");
        current.className = "activity-current-step";
        current.textContent = `${session.current_step_icon} Сейчас: ${session.current_step_title}`;
        card.append(head, current);
      } else {
        card.append(head);
      }
      container.append(card);
    }
  }

  async function loadCatalog() {
    const data = await api("/api/activities/catalog", { method: "GET" });
    catalog = data.items;
    const select = byId("activity-preview-select");
    const previous = select.value;
    select.replaceChildren();
    for (const activity of catalog) {
      const option = document.createElement("option");
      option.value = activity.id;
      option.textContent = `${activity.icon} ${activity.title}`;
      select.append(option);
    }
    if (catalog.some(item => item.id === previous)) select.value = previous;
    renderPreview();
  }

  async function loadSessions() {
    const data = await api("/api/activities/sessions", { method: "GET" });
    renderSessions(data);
  }

  async function load() {
    setStatus(byId("activity-studio-status"), "Загрузка…", "warn");
    try {
      await Promise.all([loadCatalog(), loadSessions()]);
      setStatus(byId("activity-studio-status"), "Готово", "ok");
    } catch (error) {
      setStatus(byId("activity-studio-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  byId("activity-preview-select").onchange = renderPreview;
  byId("activity-studio-refresh").onclick = load;
  return { load };
}
