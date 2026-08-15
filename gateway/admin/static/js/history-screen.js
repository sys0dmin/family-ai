import { api } from "./api-client.js?v=admin-modules-2";
import { byId, formatDateTime, getValue, setStatus } from "./dom.js?v=admin-modules-2";
import { feedbackReasonLabels } from "./quality-screen.js?v=admin-modules-2";

export function createHistoryScreen({ onFeedback, onPeriodChange }) {
  let page = 1;
  let totalPages = 0;

  function renderActivity(points) {
    const chart = byId("activity-chart");
    chart.replaceChildren();
    const maximum = Math.max(
      1,
      ...points.map(point => point.child_messages + point.assistant_messages)
    );
    for (const point of points) {
      const row = document.createElement("div");
      row.className = "activity-row";
      const day = document.createElement("span");
      day.className = "muted";
      day.textContent = new Intl.DateTimeFormat("ru-RU", {
        day: "2-digit",
        month: "2-digit"
      }).format(new Date(`${point.day}T00:00:00`));
      const track = document.createElement("div");
      track.className = "activity-track";
      const child = document.createElement("div");
      child.className = "activity-child";
      child.style.width = `${point.child_messages / maximum * 100}%`;
      const assistant = document.createElement("div");
      assistant.className = "activity-assistant";
      assistant.style.width = `${point.assistant_messages / maximum * 100}%`;
      track.append(child, assistant);
      const total = document.createElement("span");
      total.textContent = String(point.child_messages + point.assistant_messages);
      row.append(day, track, total);
      chart.append(row);
    }
  }

  function renderQuestions(questions) {
    const container = byId("frequent-questions");
    container.replaceChildren();
    if (!questions.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Вопросов за этот период пока нет";
      container.append(empty);
      return;
    }
    for (const question of questions) {
      const item = document.createElement("div");
      item.className = "question-item";
      const text = document.createElement("span");
      text.textContent = question.text;
      const count = document.createElement("span");
      count.className = "question-count";
      count.textContent = `×${question.count}`;
      item.append(text, count);
      container.append(item);
    }
  }

  function renderSummary(data) {
    byId("metric-conversations").textContent = data.conversations;
    byId("metric-child").textContent = data.child_messages;
    byId("metric-assistant").textContent = data.assistant_messages;
    byId("metric-response").textContent =
      data.average_response_seconds == null
        ? "—"
        : `${data.average_response_seconds} с`;
    renderActivity(data.daily_activity);
    renderQuestions(data.frequent_questions);
  }

  function renderConversations(data) {
    const container = byId("conversation-list");
    container.replaceChildren();
    byId("conversation-total").textContent = `Найдено: ${data.total}`;
    totalPages = data.total_pages;
    if (!data.items.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "Разговоров за этот период не найдено";
      container.append(empty);
    }
    for (const conversation of data.items) {
      const card = document.createElement("article");
      card.className = "conversation";
      const head = document.createElement("div");
      head.className = "conversation-head";
      const title = document.createElement("span");
      title.textContent = `Диалог ${conversation.conversation_id.slice(0, 8)}`;
      const meta = document.createElement("span");
      meta.textContent =
        `${formatDateTime(conversation.last_message_at)} · ` +
        `${conversation.message_count} реплик`;
      head.append(title, meta);
      const messages = document.createElement("div");
      messages.className = "messages";
      for (const message of conversation.messages) {
        const bubble = document.createElement("div");
        bubble.className = `message ${message.role}`;
        const content = document.createElement("div");
        content.textContent = message.content;
        const messageMeta = document.createElement("div");
        messageMeta.className = "message-meta";
        messageMeta.textContent =
          `${message.role === "child" ? "Лера" : "AI"} · ` +
          formatDateTime(message.created_at);
        bubble.append(content, messageMeta);
        if (message.role === "assistant") {
          const feedback = document.createElement("button");
          feedback.className = `message-feedback${message.feedback ? " active" : ""}`;
          feedback.textContent = message.feedback
            ? `⚑ ${feedbackReasonLabels[message.feedback.reason] || message.feedback.reason}`
            : "⚑ Отметить проблему";
          feedback.onclick = () => onFeedback(message);
          bubble.append(feedback);
        }
        messages.append(bubble);
      }
      card.append(head, messages);
      container.append(card);
    }
    const pagination = byId("history-pagination");
    pagination.style.display = data.total_pages > 1 ? "flex" : "none";
    byId("history-page-label").textContent =
      `Страница ${data.page} из ${Math.max(1, data.total_pages)}`;
    byId("history-prev").disabled = data.page <= 1;
    byId("history-next").disabled = data.page >= data.total_pages;
  }

  async function load(resetPage = false) {
    if (resetPage) page = 1;
    const days = getValue("history-days");
    const search = getValue("history-search").trim();
    const query = new URLSearchParams({
      days,
      page: String(page),
      page_size: "10"
    });
    if (search) query.set("search", search);
    setStatus(byId("history-status"), "Загрузка…", "warn");
    try {
      const [summary, conversations] = await Promise.all([
        api(`/api/history/summary?days=${days}`, { method: "GET" }),
        api(`/api/history/conversations?${query}`, { method: "GET" })
      ]);
      renderSummary(summary);
      renderConversations(conversations);
      setStatus(byId("history-status"), "Обновлено", "ok");
    } catch (error) {
      setStatus(byId("history-status"), `Ошибка: ${error.message}`, "err");
    }
  }

  byId("history-refresh").onclick = () => load(true);
  byId("history-days").onchange = () => {
    load(true);
    onPeriodChange();
  };
  byId("history-search").onkeydown = event => {
    if (event.key === "Enter") load(true);
  };
  byId("history-prev").onclick = () => {
    if (page > 1) {
      page -= 1;
      load();
    }
  };
  byId("history-next").onclick = () => {
    if (page < totalPages) {
      page += 1;
      load();
    }
  };
  return { load };
}
