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

  const draftFields = {
    title: "clinic-draft-title",
    patient_name: "clinic-draft-patient-name",
    mood: "clinic-draft-mood",
    complaint: "clinic-draft-complaint",
    description: "clinic-draft-description",
    opening_text: "clinic-draft-opening",
    completion_text: "clinic-draft-completion"
  };

  function fillDraftEditor() {
    const selected = catalog.find(item => item.id === byId("clinic-preview-select").value);
    if (!selected) return;
    for (const [field, id] of Object.entries(draftFields)) byId(id).value = selected[field] || "";
  }

  function renderDrafts(items) {
    const container = byId("clinic-draft-list");
    container.replaceChildren();
    if (!items.length) { container.innerHTML = '<div class="empty">Черновиков пока нет</div>'; return; }
    for (const draft of items) {
      const row = document.createElement("div"); row.className = "clinic-session-card";
      const text = document.createElement("span");
      const title = draft.payload?.case?.title || draft.payload?.title || draft.case_id;
      text.textContent = `${title} · версия ${draft.version} · ${draft.status}`;
      row.append(text);
      if (draft.status !== "published") {
        const publish = document.createElement("button"); publish.className = "secondary"; publish.textContent = draft.status === "draft" ? "Опубликовать" : "Вернуть эту версию";
        publish.onclick = async () => { await api(`/api/clinic/drafts/${draft.id}/publish`, { method: "POST" }); await load(); };
        row.append(publish);
      }
      container.append(row);
    }
  }

  async function loadDrafts() { renderDrafts(await api("/api/clinic/drafts", { method: "GET" })); }

  async function saveDraft() {
    const selected = catalog.find(item => item.id === byId("clinic-preview-select").value);
    if (!selected) return;
    const payload = {};
    for (const [field, id] of Object.entries(draftFields)) payload[field] = byId(id).value;
    setStatus(byId("clinic-draft-status"), "Сохраняю…", "warn");
    await api("/api/clinic/drafts", { method: "POST", body: JSON.stringify({ case_id: selected.id, payload }) });
    setStatus(byId("clinic-draft-status"), "Черновик сохранён", "ok");
    await loadDrafts();
  }

  function payloadFromNewPatientForm() {
    const fields = {
      patient_name: "clinic-new-patient-name",
      patient_icon: "clinic-new-patient-icon",
      mood: "clinic-new-patient-mood",
      title: "clinic-new-title",
      complaint: "clinic-new-complaint"
    };
    const payload = {};
    for (const [field, id] of Object.entries(fields)) {
      const value = byId(id).value.trim();
      if (value) payload[field] = value;
    }
    return payload;
  }

  async function createPatient() {
    const name = byId("clinic-new-patient-name").value.trim();
    const status = byId("clinic-new-patient-status");
    if (!name) {
      setStatus(status, "Укажи имя пациента", "err");
      return;
    }
    setStatus(status, "Создаю черновик…", "warn");
    try {
      await api("/api/clinic/custom-patients", {
        method: "POST",
        body: JSON.stringify({
          template_case_id: byId("clinic-new-template").value,
          payload: payloadFromNewPatientForm()
        })
      });
      setStatus(status, "Черновик создан — опубликуй его ниже", "ok");
      byId("clinic-new-patient-name").value = "";
      byId("clinic-new-title").value = "";
      byId("clinic-new-complaint").value = "";
      await loadDrafts();
    } catch (error) {
      setStatus(status, `Ошибка: ${error.message}`, "err");
    }
  }

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
    const template = byId("clinic-new-template");
    const previous = select.value;
    select.replaceChildren();
    const previousTemplate = template.value;
    template.replaceChildren();
    for (const item of catalog) {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = `${item.patient_icon} ${item.title}`;
      select.append(option);
      const templateOption = option.cloneNode(true);
      template.append(templateOption);
    }
    if (catalog.some(item => item.id === previous)) select.value = previous;
    if (catalog.some(item => item.id === previousTemplate)) template.value = previousTemplate;
    renderPreview();
    fillDraftEditor();
  }

  async function loadSessions() {
    const data = await api("/api/clinic/sessions", { method: "GET" });
    renderSessions(data);
  }

  async function load() {
    setStatus(byId("clinic-studio-status"), "Загрузка…", "warn");
    try {
      await Promise.all([loadCatalog(), loadSessions(), loadDrafts()]);
      setStatus(byId("clinic-studio-status"), "Готово", "ok");
    } catch (error) {
      setStatus(byId("clinic-studio-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  byId("clinic-preview-select").onchange = () => { renderPreview(); fillDraftEditor(); };
  byId("clinic-studio-refresh").onclick = load;
  byId("clinic-draft-save").onclick = saveDraft;
  byId("clinic-new-patient-create").onclick = createPatient;
  return { load };
}
