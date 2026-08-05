/* Training Calendar — tabs, weekly check-offs, streak. State in localStorage. */

const STORE_KEY = "tc.state.v1";
const MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];

function loadState() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY)) || { phase: "p1", weeks: {} };
  } catch {
    return { phase: "p1", weeks: {} };
  }
}
function saveState() {
  localStorage.setItem(STORE_KEY, JSON.stringify(state));
}

/* Monday-start ISO week key, e.g. "2026-W32" */
function isoWeekKey(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dow = d.getUTCDay() || 7;               // Mon=1..Sun=7
  d.setUTCDate(d.getUTCDate() + 4 - dow);       // nearest Thursday
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}
function mondayOf(date) {
  const d = new Date(date);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  d.setHours(0, 0, 0, 0);
  return d;
}
function weekLabel(date) {
  const mon = mondayOf(date);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  const f = (d) => `${MONTHS[d.getMonth()]} ${d.getDate()}`;
  return `${f(mon)} – ${f(sun)} · ${isoWeekKey(date).split("-")[1]}`;
}

const state = loadState();
const now = new Date();
const weekKey = isoWeekKey(now);
if (!Array.isArray(state.weeks[weekKey])) state.weeks[weekKey] = Array(7).fill(false);

/* prune entries older than ~15 months so storage never grows unbounded */
{
  const keys = Object.keys(state.weeks).sort();
  keys.slice(0, Math.max(0, keys.length - 66)).forEach((k) => delete state.weeks[k]);
}

function weekComplete(key) {
  const w = state.weeks[key];
  return Array.isArray(w) && w.length === 7 && w.every(Boolean);
}

/* consecutive complete weeks ending at this week (or last week if this one is in progress) */
function streak() {
  let n = 0;
  const cursor = mondayOf(now);
  if (weekComplete(weekKey)) n = 1;
  for (;;) {
    cursor.setDate(cursor.getDate() - 7);
    if (!weekComplete(isoWeekKey(cursor))) break;
    n++;
  }
  return n;
}

/* ---------- render ---------- */
const $ = (id) => document.getElementById(id);
const todayIdx = (now.getDay() + 6) % 7; // Mon=0..Sun=6

function phase() {
  return PHASES.find((p) => p.id === state.phase) || PHASES[0];
}

function renderTabs() {
  $("tabs").innerHTML = PHASES.map(
    (p) => `<button class="tab${p.id === state.phase ? " active" : ""}" role="tab"
      aria-selected="${p.id === state.phase}" data-phase="${p.id}">
      ${p.tab}<small>${p.name} · ${p.weeks}</small></button>`
  ).join("");
}

function renderMeta() {
  const p = phase();
  $("phase-meta").innerHTML =
    `<span class="miles">${p.weeklyMiles}</span>
     <span class="badge">${p.cutback}</span>
     <span class="focus">${p.focus}</span>`;
}

function renderDays() {
  const done = state.weeks[weekKey];
  $("days").innerHTML = phase().days.map(
    (d, i) => `<article class="day${done[i] ? " done" : ""}${i === todayIdx ? " today" : ""}"
      data-type="${d.type}" data-idx="${i}" role="button" aria-pressed="${done[i]}">
      <div class="row1">
        <span class="dayname">${d.day}</span>
        <span class="title">${d.title}</span>
        <span class="where">${d.where}</span>
      </div>
      <div class="spec">${d.spec}</div>
      <div class="loadbar"><div class="fill" style="width:${d.load}%"></div></div>
      <span class="check">✓</span>
    </article>`
  ).join("");
}

function renderStatus() {
  const done = state.weeks[weekKey].filter(Boolean).length;
  $("week-progress").textContent = `THIS WEEK ${done}/7`;
  $("streak-num").textContent = streak();
}

function renderAll() {
  renderTabs();
  renderMeta();
  renderDays();
  renderStatus();
}

$("week-label").textContent = weekLabel(now);
renderAll();

$("tabs").addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (!tab) return;
  state.phase = tab.dataset.phase;
  saveState();
  renderAll();
});

$("days").addEventListener("click", (e) => {
  const card = e.target.closest(".day");
  if (!card) return;
  const i = Number(card.dataset.idx);
  state.weeks[weekKey][i] = !state.weeks[weekKey][i];
  saveState();
  card.classList.toggle("done", state.weeks[weekKey][i]);
  card.setAttribute("aria-pressed", state.weeks[weekKey][i]);
  renderStatus();
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js");
}
