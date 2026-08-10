/* Fitness-app sync: JWT auth against the FitnessApp backend, weekly actuals
 * fetch, and the on-pace math. Tokens live in localStorage — acceptable for
 * a personal single-user PWA; log out to clear them.
 *
 * The backend URL can be overridden for local testing:
 *   localStorage.setItem("tc.apiBase", "http://localhost:8000")
 */

const API_BASE = localStorage.getItem("tc.apiBase")
  || "https://backend-production-e316.up.railway.app";

const TOKENS_KEY = "tc.tokens";
const ACTUALS_KEY = "tc.actuals";
const PLAN_START_KEY = "tc.planStart";

const Sync = {
  tokens() {
    try { return JSON.parse(localStorage.getItem(TOKENS_KEY)); } catch { return null; }
  },
  connected() { return !!this.tokens(); },

  async login(email, password) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Login failed (${res.status})`);
    }
    localStorage.setItem(TOKENS_KEY, JSON.stringify(await res.json()));
    if (!localStorage.getItem(PLAN_START_KEY)) {
      localStorage.setItem(PLAN_START_KEY, isoDate(mondayOf(new Date())));
    }
  },

  /* Explicit user disconnect: drop tokens AND cached actuals. */
  logout() {
    localStorage.removeItem(TOKENS_KEY);
    localStorage.removeItem(ACTUALS_KEY);
  },

  /* Auth died out from under us (refresh token expired). Drop only the
   * tokens — the cached actuals stay so the UI can label them as stale
   * instead of rendering misleading zeros. */
  expireSession() {
    localStorage.removeItem(TOKENS_KEY);
  },

  async refresh() {
    const t = this.tokens();
    if (!t?.refresh_token) return false;
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: t.refresh_token }),
    });
    if (!res.ok) { this.expireSession(); return false; }
    localStorage.setItem(TOKENS_KEY, JSON.stringify(await res.json()));
    return true;
  },

  async apiGet(path, retried) {
    const t = this.tokens();
    if (!t) throw new Error("not connected");
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { Authorization: `Bearer ${t.access_token}` },
    });
    if (res.status === 401) {
      if (!retried && await this.refresh()) return this.apiGet(path, true);
      this.expireSession();
      const err = new Error("session expired");
      err.authExpired = true;
      throw err;
    }
    if (!res.ok) throw new Error(`API ${res.status}`);
    return res.json();
  },

  /* Fetch the last 9 weeks of actuals; cache for offline rendering. */
  async fetchWeekly() {
    const tz = new Date().getTimezoneOffset();
    const data = await this.apiGet(`/calendar/weekly?weeks=9&tz_offset_minutes=${tz}`);
    localStorage.setItem(ACTUALS_KEY, JSON.stringify({ ts: Date.now(), data }));
    return data;
  },

  cachedWeekly() {
    try { return JSON.parse(localStorage.getItem(ACTUALS_KEY)); } catch { return null; }
  },
};

/* ---------- plan-week math (expected vs actual) ---------- */

function isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function planStart() {
  const v = localStorage.getItem(PLAN_START_KEY);
  return v ? new Date(`${v}T00:00:00`) : null;
}

/* 1-based plan week number for a given week's Monday; null when no start set
 * or the date precedes the plan. */
function planWeekNumber(weekMonday) {
  const start = planStart();
  if (!start) return null;
  const n = Math.floor((weekMonday - mondayOf(start)) / (7 * 86400000)) + 1;
  return n >= 1 ? n : null;
}

/* Expected mileage for plan week n: linear ramp min->max across each 8-week
 * phase, with every 4th week cut back ~25%. Past week 24, hold the peak. */
function expectedMiles(n) {
  if (!n) return null;
  const phase = PHASES[Math.min(2, Math.floor((n - 1) / 8))];
  const wip = Math.min((n - 1) % 8, 7);
  let base = phase.milesMin + (phase.milesMax - phase.milesMin) * (wip / 7);
  if (n > 24) base = PHASES[2].milesMax;
  const cutback = n % 4 === 0;
  if (cutback) base *= 0.75;
  return { miles: Math.round(base * 10) / 10, cutback, phaseKey: phase.key, week: n };
}

/* Pace verdict comparing a week's actual run miles to its expectation. */
function paceVerdict(actual, expected) {
  if (expected == null) return null;
  const ratio = expected.miles > 0 ? actual / expected.miles : 1;
  if (ratio >= 1.2) return { label: "AHEAD — EASE UP", cls: "warn" };
  if (ratio >= 0.85) return { label: "ON PACE", cls: "ok" };
  if (ratio >= 0.5) return { label: "BEHIND", cls: "warn" };
  return { label: "OFF PLAN", cls: "warn" };
}
