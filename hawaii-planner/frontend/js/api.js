// Fetch wrapper: JSON, trip token + member attribution headers, error toasts.
import { toast } from "./ui.js";

const TOKEN_KEY = "hawaii:token:v1";

export function storedToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function captureTokenFromUrl() {
  const params = new URLSearchParams(location.search);
  const token = params.get("k");
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    params.delete("k");
    const query = params.toString();
    history.replaceState(null, "", location.pathname + (query ? `?${query}` : "") + location.hash);
  }
}

export class ApiError extends Error {
  constructor(status, payload) {
    const detail = payload?.error || {};
    super(detail.message || `Request failed (${status})`);
    this.status = status;
    this.code = detail.code || "error";
    this.detail = detail;
  }
}

export async function api(path, { method = "GET", body, memberId, silent } = {}) {
  const headers = { "X-Trip-Token": storedToken() };
  if (memberId) headers["X-Member-Id"] = memberId;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    if (!silent) toast("Couldn't reach the server — check your connection", "error");
    throw err;
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    /* non-JSON body */
  }
  if (!response.ok) {
    const error = new ApiError(response.status, payload);
    // Budget conflicts get a dedicated flow; everything else toasts here.
    if (!silent && error.code !== "must_go_budget_exceeded") {
      toast(error.message, "error");
    }
    throw error;
  }
  return payload;
}
