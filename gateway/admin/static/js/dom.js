export function byId(id) {
  return document.getElementById(id);
}

export function getValue(id) {
  return byId(id).value;
}

export function setValue(id, value) {
  byId(id).value = value ?? "";
}

export function setStatus(element, text, mode) {
  element.style.display = "inline-block";
  element.textContent = text;
  element.className = `status ${mode}`;
}

export function formatDateTime(value) {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}
