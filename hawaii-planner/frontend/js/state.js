// Single state object + render dispatch + version polling + freshness.
import { api } from "./api.js";

const MEMBER_KEY = "hawaii:member:v1";
const LAST_SEEN_KEY = "hawaii:lastSeen:v1";
const POLL_MS = 10_000;

export const state = {
  member: null, // {id, name, color}
  data: null, // bootstrap payload
  tab: "schedule", // schedule | ideas | eats
  dayId: null,
  ideasRegion: null, // region filter or null = all
  eatsRegion: null,
  eatsSort: "ranked", // ranked | newest
  reorderMode: false,
  // Freshness snapshot taken at boot; visiting a tab updates storage only.
  seenAtBoot: { ideas: 0, eats: 0 },
};

let renderFn = () => {};
export function onRender(fn) {
  renderFn = fn;
}
export function render() {
  renderFn();
}

// ── Member persistence ─────────────────────────────────────
export function storedMember() {
  try {
    return JSON.parse(localStorage.getItem(MEMBER_KEY));
  } catch {
    return null;
  }
}
export function saveMember(member) {
  state.member = member;
  localStorage.setItem(MEMBER_KEY, JSON.stringify(member));
}

// ── Freshness ──────────────────────────────────────────────
function loadSeen() {
  try {
    return JSON.parse(localStorage.getItem(LAST_SEEN_KEY)) || {};
  } catch {
    return {};
  }
}
export function snapshotSeen() {
  const stored = loadSeen();
  state.seenAtBoot = { ideas: stored.ideas || 0, eats: stored.eats || 0 };
}
export function markSeen(tabKey) {
  const stored = loadSeen();
  stored[tabKey] = Date.now();
  localStorage.setItem(LAST_SEEN_KEY, JSON.stringify(stored));
}
export function isNew(idea) {
  const key = idea.kind === "restaurant" ? "eats" : "ideas";
  const baseline = state.seenAtBoot[key];
  if (!baseline) return false; // first ever visit: nothing is "new"
  const created = Date.parse(idea.created_at || "") || 0;
  const mine = state.member && idea.created_by_member_id === state.member.id;
  return created > baseline && !mine;
}
export function tabHasNew(tabKey) {
  if (!state.data) return false;
  const kind = tabKey === "eats" ? "restaurant" : "activity";
  return state.data.ideas.some((idea) => idea.kind === kind && isNew(idea));
}

// ── Data refresh + in-place updates ────────────────────────
export async function refresh() {
  state.data = await api("/api/bootstrap");
  if (!state.dayId || !state.data.days.some((day) => day.id === state.dayId)) {
    state.dayId = defaultDayId();
  }
  render();
}

function defaultDayId() {
  const days = state.data?.days || [];
  if (!days.length) return null;
  // Trip dates are Hawaii wall-clock — compute "today" in HST, not UTC.
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Pacific/Honolulu" });
  const current = days.find((day) => day.date && day.date >= today);
  return (current || days[0]).id;
}

// A mutation response carries the post-mutation version. A gap larger than one
// means someone else's change landed in between — refetch so it isn't skipped.
function adoptVersion(version) {
  if (!version) return;
  const gap = version - state.data.version;
  state.data.version = Math.max(state.data.version, version);
  if (gap > 1) refresh();
}

export function applyDay(payload) {
  if (!payload?.day) return;
  const index = state.data.days.findIndex((day) => day.id === payload.day.id);
  if (index >= 0) state.data.days[index] = payload.day;
  else state.data.days.push(payload.day);
  adoptVersion(payload.version);
  syncScheduledIds();
  render();
}

export function applyIdea(payload) {
  if (!payload?.idea) return;
  const index = state.data.ideas.findIndex((idea) => idea.id === payload.idea.id);
  if (index >= 0) state.data.ideas[index] = payload.idea;
  else state.data.ideas.push(payload.idea);
  adoptVersion(payload.version);
  render();
}

// Recompute idea.scheduled_day_ids from the day payloads we hold — keeps
// pool ✓-chips honest after item add/remove without a full refetch.
function syncScheduledIds() {
  const map = {};
  for (const day of state.data.days) {
    for (const item of day.items) {
      if (item.idea_id) (map[item.idea_id] ||= []).push(day.id);
    }
  }
  for (const idea of state.data.ideas) {
    idea.scheduled_day_ids = map[idea.id] || [];
  }
}

// ── Version polling ────────────────────────────────────────
async function poll() {
  if (document.visibilityState !== "visible" || !state.data) return;
  try {
    const payload = await api("/api/version", { silent: true });
    if (payload.version !== state.data.version) await refresh();
  } catch {
    /* transient — next tick retries */
  }
}

export function startPolling() {
  setInterval(poll, POLL_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") poll();
  });
}
