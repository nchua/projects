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

const ROMAN = ["I", "II", "III", "IV", "V"];

function phase() {
  return PHASES.find((p) => p.key === state.phase) || PHASES[0];
}

function renderTabs() {
  $("tabs").innerHTML = PHASES.map(
    (p, i) => `<button class="tab${p.key === state.phase ? " active" : ""}" role="tab"
      aria-selected="${p.key === state.phase}" data-phase="${p.key}">
      Phase ${ROMAN[i]}<small>${p.label}</small></button>`
  ).join("");
}

function renderMeta() {
  const p = phase();
  $("phase-meta").innerHTML =
    `<span class="miles">${p.sub}</span>
     <span class="badge">EVERY 4TH WK: −25% MILEAGE</span>
     <span class="focus">${p.note}</span>`;
}

/* actuals state: latest /calendar/weekly payload (fetched or cached) */
let actualWeeks = null;
/* last doSync outcome: null (ok/not run) | "expired" (auth) | "failed" (network/5xx) */
let syncError = null;

function currentWeekActuals() {
  if (!actualWeeks?.length) return null;
  const monday = isoDate(mondayOf(now));
  return actualWeeks.find((w) => w.week_start === monday) || null;
}

/* "SQ 245×3" style abbreviation: keyword map, else last word truncated */
const LIFT_ABBREV = [
  ["overhead press", "OHP"], ["bench", "BP"], ["squat", "SQ"],
  ["deadlift", "DL"], ["row", "ROW"], ["pull-up", "PULL"], ["chin", "CHIN"],
  ["lunge", "LUNGE"], ["leg press", "LP"], ["curl", "CURL"], ["dip", "DIP"],
];
function abbrevLift(name) {
  const n = name.toLowerCase();
  for (const [k, v] of LIFT_ABBREV) if (n.includes(k)) return v;
  return name.split(" ").pop().slice(0, 5).toUpperCase();
}
function liftSummary(lift) {
  return lift.exercises.slice(0, 4).map((ex) => {
    const top = ex.sets.reduce((a, b) => (b.weight > a.weight ? b : a), ex.sets[0]);
    return `${abbrevLift(ex.name)} ${top.weight}×${top.reps}`;
  }).join(" · ");
}

function fmtPace(sec) {
  if (!sec) return null;
  return `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, "0")}/MI`;
}

function dayActualLine(dayIdx) {
  const week = currentWeekActuals();
  if (!week) return null;
  const runs = week.runs.filter((r) => r.day_index === dayIdx);
  const lifts = week.lifts.filter((l) => l.day_index === dayIdx);
  const parts = [];
  for (const r of runs) {
    const bits = [];
    if (r.distance_miles != null) bits.push(`${r.distance_miles} MI`);
    const pace = fmtPace(r.pace_sec_per_mile);
    if (pace) bits.push(pace);
    else if (r.duration_minutes != null) bits.push(`${r.duration_minutes} MIN`);
    if (r.avg_heart_rate != null) bits.push(`${r.avg_heart_rate} BPM`);
    parts.push(bits.join(" · ") || (r.activity_type || "ACTIVITY").toUpperCase());
  }
  for (const l of lifts) parts.push(liftSummary(l));
  return parts.length ? parts.join("  |  ") : null;
}

/* Distance-weighted average pace + duration-weighted avg HR for a week's runs. */
function weekRunStats(w) {
  const runs = w.runs.filter((r) => r.is_run && r.distance_miles);
  const totalMi = runs.reduce((a, r) => a + r.distance_miles, 0);
  const paced = runs.filter((r) => r.pace_sec_per_mile);
  const pacedMi = paced.reduce((a, r) => a + r.distance_miles, 0);
  const pace = pacedMi
    ? paced.reduce((a, r) => a + r.pace_sec_per_mile * r.distance_miles, 0) / pacedMi
    : null;
  const hrRuns = runs.filter((r) => r.avg_heart_rate);
  const hr = hrRuns.length
    ? Math.round(hrRuns.reduce((a, r) => a + r.avg_heart_rate, 0) / hrRuns.length)
    : null;
  return { totalMi, pace, hr };
}

/* Auto-check days that have a synced session of the matching kind. */
function applyAutoCheck() {
  const week = currentWeekActuals();
  if (!week) return;
  const done = state.weeks[weekKey];
  const p = phase();
  for (let i = 0; i < 7; i++) {
    const hasRun = week.runs.some((r) => r.day_index === i);
    const hasLift = week.lifts.some((l) => l.day_index === i);
    const type = p.days[i].type;
    if ((type === "run" && hasRun) || (type === "lift" && hasLift) ||
        (type === "light" && (hasRun || hasLift))) {
      done[i] = true;
    }
  }
  saveState();
}

function renderDays() {
  const done = state.weeks[weekKey];
  $("days").innerHTML = phase().days.map((d, i) => {
    const actual = dayActualLine(i);
    return `<article class="day${done[i] ? " done" : ""}${i === todayIdx ? " today" : ""}"
      data-type="${d.type}" data-idx="${i}" role="button" aria-pressed="${done[i]}">
      <div class="row1">
        <span class="dayname">${d.name.slice(0, 3).toUpperCase()}</span>
        <span class="title">${d.title}</span>
      </div>
      <div class="items">${d.items.map(
        ([what, spec]) => `<div class="item"><span class="what">${what}</span><span class="val">${spec}</span></div>`
      ).join("")}</div>
      ${d.note ? `<div class="note">${d.note}</div>` : ""}
      ${actual ? `<div class="actual mono">LOGGED&nbsp; ${actual}</div>` : ""}
      <div class="loadbar"><div class="fill" style="width:${d.load}%"></div></div>
      <span class="check">✓</span>
    </article>`;
  }).join("");
}

/* ---------- sync strip + pace report ---------- */

function renderSyncbar() {
  const bar = $("syncbar");
  bar.hidden = false;
  if (!Sync.connected()) {
    // A dead session (expired refresh token) lands here too — say so
    // instead of presenting like a never-connected install.
    const label = syncError === "expired"
      ? "SESSION EXPIRED — TAP TO RECONNECT"
      : "CONNECT FITNESS APP";
    bar.innerHTML = `<button class="connect-btn" id="connect-btn">${label}</button>`;
    $("report").hidden = true;
    return;
  }
  const week = currentWeekActuals();
  const miles = week ? week.run_miles : 0;
  const liftCount = week ? week.lift_sessions : 0;
  const exp = expectedMiles(planWeekNumber(mondayOf(now)));
  // Sync failed and we're showing a cached payload — label it stale rather
  // than passing off old numbers (or zeros) as this week's progress.
  if (syncError) {
    const ts = Sync.cachedWeekly()?.ts;
    const age = ts ? Math.max(0, Math.round((Date.now() - ts) / 86400000)) : null;
    bar.innerHTML = `
      <div class="sync-line" id="sync-toggle" role="button">
        <span class="mono">WK ${exp ? exp.week : "?"} · SYNC FAILED</span>
        <span class="pace warn mono">${age != null ? `SHOWING ${age === 0 ? "TODAY'S" : age + "D OLD"} DATA` : "NO DATA"}</span>
        <span class="chev" id="report-chev">▾</span>
      </div>`;
    return;
  }
  // Judge the week in progress against a pro-rated target (through today),
  // not the full-week number — Monday shouldn't start out "BEHIND".
  const verdict = exp
    ? paceVerdict(miles, { ...exp, miles: Math.round(exp.miles * (todayIdx + 1) / 7 * 10) / 10 })
    : null;
  bar.innerHTML = `
    <div class="sync-line" id="sync-toggle" role="button">
      <span class="mono">WK ${exp ? exp.week : "?"} · ${miles.toFixed(1)}${exp ? "/" + exp.miles : ""} MI · ${liftCount} LIFT${liftCount === 1 ? "" : "S"}</span>
      ${verdict ? `<span class="pace ${verdict.cls} mono">${verdict.label}</span>` : ""}
      <span class="chev" id="report-chev">▾</span>
    </div>`;
}

function renderReport() {
  const el = $("report");
  if (!Sync.connected() || !actualWeeks?.length) { el.hidden = true; return; }

  // Weekly running table: last 5 weeks incl. current — expected vs actual
  // miles, longest run, distance-weighted pace, avg HR. Pace falling while
  // HR holds (or HR falling at the same pace) is the aerobic-progress signal.
  const rows = actualWeeks.slice(-5).map((w) => {
    const monday = new Date(`${w.week_start}T00:00:00`);
    const n = planWeekNumber(monday);
    const exp = expectedMiles(n);
    const longest = Math.max(0, ...w.runs.filter((r) => r.is_run).map((r) => r.distance_miles || 0));
    const stats = weekRunStats(w);
    const v = paceVerdict(w.run_miles, exp);
    const isCurrent = w.week_start === isoDate(mondayOf(now));
    const wkCls = [isCurrent ? "current" : "", !isCurrent && v ? v.cls + "-row" : ""].join(" ");
    return `<tr class="${wkCls}">
      <td>${n ? "W" + n : w.week_start.slice(5)}${exp?.cutback ? "↓" : ""}</td>
      <td>${w.run_miles.toFixed(1)}${exp ? " / " + exp.miles : ""}</td>
      <td>${longest ? longest.toFixed(1) : "—"}</td>
      <td>${stats.pace ? fmtPace(stats.pace).replace("/MI", "") : "—"}</td>
      <td>${stats.hr ?? "—"}</td>
    </tr>`;
  }).join("");

  // Lift trend: best e1RM this week vs best in the prior 4 weeks.
  const KEY_LIFTS = ["Squat", "Deadlift", "Bench", "Overhead"];
  const recent = actualWeeks.slice(-1)[0];
  const prior = actualWeeks.slice(-5, -1);
  const bestE1rm = (weeks, key) => Math.max(0, ...weeks.flatMap((w) => w.lifts)
    .flatMap((l) => l.exercises)
    .filter((ex) => ex.name.toLowerCase().includes(key.toLowerCase()))
    .map((ex) => ex.best_e1rm || 0));
  const liftRows = KEY_LIFTS.map((key) => {
    const nowBest = bestE1rm([recent], key);
    const priorBest = bestE1rm(prior, key);
    if (!nowBest && !priorBest) return "";
    const delta = nowBest && priorBest ? nowBest - priorBest : null;
    const arrow = delta == null ? "" : delta > 1 ? "▲" : delta < -1 ? "▼" : "→";
    return `<tr><td>${key.toUpperCase()}</td>
      <td>${nowBest ? Math.round(nowBest) : "—"}</td>
      <td>${priorBest ? Math.round(priorBest) : "—"}</td>
      <td class="${delta > 1 ? "ok" : delta < -1 ? "warn" : ""}">${arrow}${delta != null ? " " + (delta > 0 ? "+" : "") + Math.round(delta) : ""}</td>
    </tr>`;
  }).join("");

  const p = phase();
  const longestRecent = Math.max(0, ...(recent?.runs || []).filter((r) => r.is_run).map((r) => r.distance_miles || 0));
  el.innerHTML = `
    <div class="report-block">
      <h3>RUNNING · EXPECTED VS ACTUAL</h3>
      <table class="mono"><thead><tr><th>WK</th><th>MI (ACT/EXP)</th><th>LONG</th><th>/MI</th><th>BPM</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="report-note">↓ = planned −25% cutback week · long-run target this phase: ${p.longRunMi} mi (longest this wk: ${longestRecent ? longestRecent.toFixed(1) : "0"}) · progress = pace dropping at the same HR</div>
    </div>
    <div class="report-block">
      <h3>LIFTS · BEST E1RM (THIS WK VS PRIOR 4)</h3>
      <table class="mono"><thead><tr><th>LIFT</th><th>NOW</th><th>PRIOR</th><th>Δ</th></tr></thead>
      <tbody>${liftRows || `<tr><td colspan="4">no lift data yet</td></tr>`}</tbody></table>
      <div class="report-note">this wk: ${recent ? recent.lift_sessions : 0} session${recent?.lift_sessions === 1 ? "" : "s"} · ${recent ? recent.total_sets : 0} sets</div>
    </div>
    <div class="report-actions">
      <button id="sync-refresh">REFRESH</button>
      <button id="sync-logout">DISCONNECT</button>
    </div>`;
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
  renderSyncbar();
}

$("week-label").textContent = weekLabel(now);
renderAll();

/* ---------- sync bootstrap + UI events ---------- */

function loadActuals(data) {
  actualWeeks = data.weeks;
  applyAutoCheck();
  renderAll();
  renderReport();
}

async function doSync() {
  syncError = null;
  try {
    loadActuals(await Sync.fetchWeekly());
  } catch (e) {
    syncError = e.authExpired ? "expired" : "failed";
    const cached = Sync.cachedWeekly();
    if (cached && Sync.connected()) {
      loadActuals(cached.data);
    } else {
      // Session expired (tokens gone) or nothing cached: re-render so the
      // strip reflects reality instead of keeping the pre-sync optimism.
      renderAll();
      $("report").hidden = true;
    }
  }
}

if (Sync.connected()) {
  const cached = Sync.cachedWeekly();
  if (cached) loadActuals(cached.data);
  doSync();
}

document.addEventListener("click", async (e) => {
  const id = e.target.id;
  if (id === "connect-btn") {
    $("plan-start").value = localStorage.getItem("tc.planStart") || isoDate(mondayOf(now));
    $("login-error").textContent = "";
    $("login-dialog").showModal();
  } else if (id === "login-cancel") {
    $("login-dialog").close();
  } else if (id === "sync-toggle" || e.target.closest?.("#sync-toggle")) {
    if (Sync.connected()) {
      const r = $("report");
      r.hidden = !r.hidden;
      if (!r.hidden) renderReport();
    }
  } else if (id === "sync-refresh") {
    e.target.textContent = "SYNCING…";
    await doSync();
  } else if (id === "sync-logout") {
    Sync.logout();
    actualWeeks = null;
    $("report").hidden = true;
    renderAll();
  }
});

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("login-submit");
  btn.disabled = true;
  btn.textContent = "Connecting…";
  try {
    const start = $("plan-start").value;
    if (start) localStorage.setItem("tc.planStart", start);
    await Sync.login($("login-email").value.trim(), $("login-password").value);
    $("login-dialog").close();
    await doSync();
  } catch (err) {
    $("login-error").textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Connect";
  }
});

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

/* iOS keeps standalone web apps alive in the background, so a reopen is
 * usually NOT a page load — without this, the page only ever synced once
 * and sat on stale actuals (e.g. a run imported minutes after load never
 * appeared). On return to foreground: reload if the calendar date rolled
 * (load-time `now`/week state would be wrong), else just re-fetch. */
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  if (isoDate(new Date()) !== isoDate(now)) { location.reload(); return; }
  if (Sync.connected()) doSync();
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js");
}
