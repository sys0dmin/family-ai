import { byId } from "./dom.js?v=admin-modules-2";

const STORAGE_KEY = "family-ai.admin.boxed-layout";

function readPreference() {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === null ? true : value !== "false";
  } catch (_) {
    return true;
  }
}

function storePreference(boxed) {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(boxed));
  } catch (_) {
    // Private browsing may deny storage; the current-page preference still works.
  }
}

export function createLayoutPreference() {
  const checkbox = byId("admin-boxed-layout");

  function apply(boxed, persist = false) {
    checkbox.checked = boxed;
    document.body.classList.toggle("admin-fluid-layout", !boxed);
    if (persist) storePreference(boxed);
  }

  checkbox.addEventListener("change", () => apply(checkbox.checked, true));
  apply(readPreference());

  return { apply };
}
