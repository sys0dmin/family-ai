    import {
      api,
      createBrowserSession,
      deleteBrowserSession
    } from "./api-client.js?v=admin-modules-2";
    import { getValue, setStatus, setValue } from "./dom.js?v=admin-modules-3";
    import { createAgentsScreen } from "./agents-screen.js?v=admin-modules-3";
    import { createHistoryScreen } from "./history-screen.js?v=admin-modules-2";
    import { createHelpScreen } from "./help-screen.js?v=admin-modules-2";
    import { createInfrastructureScreen } from "./infrastructure-screen.js?v=admin-modules-3";
    import { createLayoutPreference } from "./layout-preference.js?v=admin-modules-2";
    import { createActivityScreen } from "./activity-screen.js?v=admin-modules-2";
    import { createCalibrationScreen } from "./calibration-screen.js?v=admin-modules-3";
    import { createMemoryScreen } from "./memory-screen.js?v=admin-modules-2";
    import { createNavigation, hideAllScreens } from "./navigation.js?v=admin-modules-2";
    import { createQualityScreen } from "./quality-screen.js?v=admin-modules-2";
    import { createSafetyPolicyScreen } from "./safety-policy-screen.js?v=admin-modules-2";
    import { createSettingsScreen } from "./settings-screen.js?v=admin-modules-3";
    import { createStudioScreen } from "./studio-screen.js?v=admin-modules-3";

    const authCard = document.getElementById("auth-card");
    const passwordCard = document.getElementById("password-card");
    const mainNav = document.getElementById("main-nav");
    const authStatus = document.getElementById("auth-status");
    const passwordStatus = document.getElementById("password-status");
    let infrastructureTimer = null;
    let calibrationTimer = null;
    let navigate;

    function switchTab(tab) {
      navigate(tab);
    }

    async function loadSettings() {
      const data = await settingsScreen.load();
      document.body.classList.add("authenticated");
      authCard.style.display = "none";
      if (data.must_change_password) {
        passwordCard.style.display = "block";
        mainNav.style.display = "none";
        hideAllScreens();
        setStatus(passwordStatus, "Требуется сменить пароль", "warn");
      } else {
        passwordCard.style.display = "none";
        mainNav.style.display = "flex";
        switchTab("settings");
        settingsScreen.setSaveStatus("Настройки загружены", "ok");
      }
    }

    async function login() {
      const username = getValue("username").trim();
      const password = getValue("password");

      authStatus.textContent = "Проверка доступа...";
      try {
        await createBrowserSession(username, password);
        await loadSettings();
        authStatus.textContent = "";
      } catch (error) {
        document.body.classList.remove("authenticated");
        authStatus.textContent = `Ошибка авторизации: ${error.message}`;
      }
    }

    const safetyPolicyScreen = createSafetyPolicyScreen({
      openAgents: () => switchTab("agents")
    });
    let qualityScreen;
    const historyScreen = createHistoryScreen({
      onFeedback: message => qualityScreen.openFeedback(message),
      onPeriodChange: () => qualityScreen.loadSummary()
    });
    qualityScreen = createQualityScreen({
      reloadHistory: () => historyScreen.load()
    });
    const memoryScreen = createMemoryScreen();
    const activityScreen = createActivityScreen({
      openMemory: proposal => {
        memoryScreen.prefillLearningOutcome(proposal);
        switchTab("memory");
      }
    });
    const infrastructureScreen = createInfrastructureScreen();
    const calibrationScreen = createCalibrationScreen();
    const settingsScreen = createSettingsScreen();
    const agentsScreen = createAgentsScreen();
    const studioScreen = createStudioScreen(agentsScreen);
    createLayoutPreference();
    const helpScreen = createHelpScreen({
      openSection: tab => switchTab(tab)
    });
    navigate = createNavigation(tab => {
      clearInterval(infrastructureTimer);
      infrastructureTimer = null;
      clearInterval(calibrationTimer);
      calibrationTimer = null;
      if (tab === "settings") settingsScreen.loadRevisions();
      if (tab === "agents") agentsScreen.load();
      if (tab === "studio") {
        studioScreen.load();
        qualityScreen.loadCases();
        activityScreen.load();
        calibrationScreen.loadStatus();
        calibrationScreen.loadRuntimeSettings();
        calibrationTimer = setInterval(calibrationScreen.loadStatus, 5000);
      }
      if (tab === "safety") safetyPolicyScreen.load();
      if (tab === "memory") memoryScreen.load();
      if (tab === "infrastructure") {
        infrastructureScreen.load();
        infrastructureTimer = setInterval(infrastructureScreen.load, 15000);
      }
      if (tab === "history") {
        historyScreen.load(true);
        qualityScreen.loadSummary();
      }
      if (tab === "help") helpScreen.load();
    });

    document.getElementById("login-btn").onclick = login;
    for (const id of ["username", "password"]) {
      document.getElementById(id).addEventListener("keydown", event => {
        if (event.key === "Enter") login();
      });
    }

    document.getElementById("logout-btn").onclick = async () => {
      try {
        await deleteBrowserSession();
      } catch (_) {
        // Локальное состояние всё равно сбрасывается.
      }
      clearInterval(infrastructureTimer);
      infrastructureTimer = null;
      clearInterval(calibrationTimer);
      calibrationTimer = null;
      setValue("password", "");
      document.body.classList.remove("authenticated");
      authCard.style.display = "block";
      authStatus.textContent = "";
    };

    document.getElementById("child-ui-link").href = `${location.protocol}//${location.hostname}:8000`;

    document.getElementById("reload-btn").onclick = async () => {
      try {
        await loadSettings();
      } catch (error) {
        settingsScreen.setSaveStatus(`Ошибка: ${error.message}`, "err");
      }
    };

    document.getElementById("settings-tab").onclick = () => switchTab("settings");
    document.getElementById("agents-tab").onclick = () => switchTab("agents");
    document.getElementById("studio-tab").onclick = () => switchTab("studio");
    document.getElementById("safety-tab").onclick = () => switchTab("safety");
    document.getElementById("memory-tab").onclick = () => switchTab("memory");
    document.getElementById("infrastructure-tab").onclick = () => switchTab("infrastructure");
    document.getElementById("history-tab").onclick = () => switchTab("history");
    document.getElementById("help-tab").onclick = () => switchTab("help");

    document.getElementById("change-password-btn").onclick = async () => {
      const password = getValue("new_admin_password");
      const confirm = getValue("new_admin_password_confirm");

      if (password.length < 8) {
        setStatus(passwordStatus, "Минимум 8 символов", "err");
        return;
      }
      if (password !== confirm) {
        setStatus(passwordStatus, "Пароли не совпадают", "err");
        return;
      }

      try {
        await api("/api/change-password", {
          method: "POST",
          body: JSON.stringify({ new_password: password })
        });

        setValue("password", password);
        setValue("new_admin_password", "");
        setValue("new_admin_password_confirm", "");
        setStatus(passwordStatus, "Пароль изменён", "ok");
        await createBrowserSession(getValue("username").trim(), password);
        await loadSettings();
      } catch (error) {
        setStatus(passwordStatus, `Ошибка смены пароля: ${error.message}`, "err");
      }
    };

    async function restoreBrowserSession() {
      try {
        await loadSettings();
      } catch (_) {
        // Нет действующей cookie-сессии: остаёмся на форме входа.
      }
    }

    restoreBrowserSession();
