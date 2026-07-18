const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

function errorMessage(body, status) {
  if (typeof body.detail === "string") return body.detail;
  if (
    body.detail
    && typeof body.detail === "object"
    && typeof body.detail.message === "string"
  ) {
    return body.detail.message;
  }
  if (Array.isArray(body.detail)) {
    const messages = body.detail
      .map((item) => item?.msg)
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  return `Request failed (${status})`;
}

export async function api(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(errorMessage(body, response.status));
  return body;
}
