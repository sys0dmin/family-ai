const pageCopy = {
  settings: ["Настройки", "System configuration"],
  agents: ["Агенты", "Agent studio"],
  studio: ["Тест-студия", "Prompt & voice laboratory"],
  safety: ["Safety Policy", "Child safety control"],
  infrastructure: ["Инфраструктура", "Project operations"],
  history: ["Аналитика", "Conversation intelligence"]
};

const screenIds = {
  settings: "settings-card",
  agents: "agents-card",
  studio: "studio-card",
  safety: "safety-policy-card",
  infrastructure: "infrastructure-card",
  history: "history-card"
};

export function createNavigation(onEnter) {
  return function switchTab(name) {
    for (const [screenName, screenId] of Object.entries(screenIds)) {
      const active = screenName === name;
      document.getElementById(screenId).style.display = active ? "block" : "none";
      const button = document.getElementById(`${screenName}-tab`);
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    }
    document.getElementById("page-title").textContent = pageCopy[name][0];
    document.getElementById("page-kicker").textContent = pageCopy[name][1];
    onEnter(name);
  };
}

export function hideAllScreens() {
  for (const screenId of Object.values(screenIds)) {
    document.getElementById(screenId).style.display = "none";
  }
}
