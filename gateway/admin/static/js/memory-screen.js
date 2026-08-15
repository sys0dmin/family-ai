import { api } from "./api-client.js?v=admin-modules-2";
import { byId, formatDateTime, getValue, setStatus, setValue } from "./dom.js?v=admin-modules-2";

const categoryLabels = {
  interest: "Интерес",
  preference: "Предпочтение",
  learning_progress: "Учебный прогресс"
};

const sourceLabels = {
  parent_observation: "Наблюдение родителя",
  child_statement: "Слова Леры",
  learning_activity: "Учебное занятие"
};

function todayLocal() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function createMemoryScreen() {
  let memories = [];
  let editingId = null;

  function resetForm() {
    editingId = null;
    byId("memory-form-title").textContent = "Новая запись";
    byId("memory-save").textContent = "Подтвердить запись";
    byId("memory-cancel").hidden = true;
    setValue("memory-category", "interest");
    setValue("memory-topic", "");
    setValue("memory-summary", "");
    setValue("memory-source-type", "parent_observation");
    setValue("memory-source-date", todayLocal());
    setValue("memory-source-note", "");
  }

  function updateCounters() {
    byId("memory-total").textContent = String(memories.length);
    byId("memory-interest-count").textContent =
      String(memories.filter(item => item.category === "interest").length);
    byId("memory-preference-count").textContent =
      String(memories.filter(item => item.category === "preference").length);
    byId("memory-progress-count").textContent =
      String(memories.filter(item => item.category === "learning_progress").length);
  }

  function beginEdit(memory) {
    editingId = memory.id;
    byId("memory-form-title").textContent = "Редактирование записи";
    byId("memory-save").textContent = "Подтвердить изменения";
    byId("memory-cancel").hidden = false;
    setValue("memory-category", memory.category);
    setValue("memory-topic", memory.topic);
    setValue("memory-summary", memory.summary);
    setValue("memory-source-type", memory.source_type);
    setValue("memory-source-date", memory.source_date);
    setValue("memory-source-note", memory.source_note || "");
    byId("memory-topic").focus();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function remove(memory) {
    if (!confirm(`Удалить запись «${memory.topic}» навсегда? Она сразу перестанет попадать в новые ответы.`)) return;
    try {
      await api(`/api/memories/${encodeURIComponent(memory.id)}`, {
        method: "DELETE"
      });
      if (editingId === memory.id) resetForm();
      await load();
      setStatus(byId("memory-status"), "Запись удалена", "ok");
    } catch (error) {
      setStatus(byId("memory-status"), `Ошибка удаления: ${error.message}`, "err");
    }
  }

  function render() {
    updateCounters();
    const filter = getValue("memory-filter");
    const visible = filter
      ? memories.filter(item => item.category === filter)
      : memories;
    const container = byId("memory-list");
    container.replaceChildren();
    if (!visible.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = filter
        ? "В этой категории записей пока нет"
        : "Долгосрочная память пока пуста";
      container.append(empty);
      return;
    }

    for (const memory of visible) {
      const card = document.createElement("article");
      card.className = `memory-item ${memory.category}`;

      const head = document.createElement("div");
      head.className = "memory-item-head";
      const identity = document.createElement("div");
      const category = document.createElement("span");
      category.className = `memory-category ${memory.category}`;
      category.textContent = categoryLabels[memory.category];
      const topic = document.createElement("h3");
      topic.textContent = memory.topic;
      identity.append(category, topic);
      const actions = document.createElement("div");
      actions.className = "memory-actions";
      const edit = document.createElement("button");
      edit.className = "secondary";
      edit.textContent = "Изменить";
      edit.onclick = () => beginEdit(memory);
      const removeButton = document.createElement("button");
      removeButton.className = "danger";
      removeButton.textContent = "Удалить";
      removeButton.onclick = () => remove(memory);
      actions.append(edit, removeButton);
      head.append(identity, actions);

      const summary = document.createElement("p");
      summary.className = "memory-summary";
      summary.textContent = memory.summary;
      const source = document.createElement("div");
      source.className = "memory-source";
      source.textContent =
        `${sourceLabels[memory.source_type]} · ${memory.source_date}` +
        (memory.source_note ? ` · ${memory.source_note}` : "");
      const meta = document.createElement("div");
      meta.className = "memory-meta";
      meta.textContent =
        `Подтвердил: ${memory.updated_by} · ${formatDateTime(memory.confirmed_at)}`;
      card.append(head, summary, source, meta);
      container.append(card);
    }
  }

  async function load() {
    setStatus(byId("memory-status"), "Загрузка…", "warn");
    try {
      const data = await api("/api/memories", { method: "GET" });
      memories = data.items;
      render();
      setStatus(byId("memory-status"), "Память синхронизирована", "ok");
    } catch (error) {
      setStatus(byId("memory-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  async function save() {
    const topic = getValue("memory-topic").trim();
    const summary = getValue("memory-summary").trim();
    const sourceDate = getValue("memory-source-date");
    if (topic.length < 2 || summary.length < 3 || !sourceDate) {
      setStatus(
        byId("memory-status"),
        "Заполните тему, подтверждённое сведение и дату источника",
        "warn"
      );
      return;
    }
    const payload = {
      category: getValue("memory-category"),
      topic,
      summary,
      source_type: getValue("memory-source-type"),
      source_date: sourceDate,
      source_note: getValue("memory-source-note").trim() || null
    };
    const path = editingId
      ? `/api/memories/${encodeURIComponent(editingId)}`
      : "/api/memories";
    try {
      await api(path, {
        method: editingId ? "PUT" : "POST",
        body: JSON.stringify(payload)
      });
      resetForm();
      await load();
      setStatus(byId("memory-status"), "Запись подтверждена", "ok");
    } catch (error) {
      setStatus(byId("memory-status"), `Ошибка сохранения: ${error.message}`, "err");
    }
  }

  function prefillLearningOutcome({ topic, summary }) {
    resetForm();
    setValue("memory-category", "learning_progress");
    setValue("memory-topic", topic);
    setValue("memory-summary", summary);
    setValue("memory-source-type", "learning_activity");
    setValue("memory-source-date", todayLocal());
    setValue("memory-source-note", "Предложено после завершения короткого занятия");
    byId("memory-topic").focus();
  }

  byId("memory-refresh").onclick = load;
  byId("memory-filter").onchange = render;
  byId("memory-save").onclick = save;
  byId("memory-cancel").onclick = resetForm;
  resetForm();

  return { load, prefillLearningOutcome };
}
