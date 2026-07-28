let transientAuthHeader = "";

export async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: {
      ...(transientAuthHeader ? { "Authorization": transientAuthHeader } : {}),
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`HTTP ${response.status}: ${body || response.statusText}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

export async function requestBlob(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: {
      ...(transientAuthHeader ? { "Authorization": transientAuthHeader } : {}),
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.blob();
}

export async function createBrowserSession(username, password) {
  transientAuthHeader = "Basic " + btoa(`${username}:${password}`);
  try {
    const response = await fetch("/api/session", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Authorization": transientAuthHeader }
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } finally {
    transientAuthHeader = "";
  }
}

export async function deleteBrowserSession() {
  transientAuthHeader = "";
  await fetch("/api/session", {
    method: "DELETE",
    credentials: "same-origin"
  });
}
