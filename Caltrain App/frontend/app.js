/* Caltrain Commute Helper — vanilla JS, no build step.
   All dynamic text is set via textContent (never innerHTML with API data).
   All times render in America/Los_Angeles — the server runs UTC. */
"use strict";

const TZ = "America/Los_Angeles";
const STORAGE_KEY = "caltrain:favorites:v1";
const MAX_FAVORITES = 6;
const COLLAPSED_LIMIT = 4;
const EXPANDED_LIMIT = 10;
const REFRESH_INTERVAL_MS = 60_000;
const VISIBILITY_REFRESH_AFTER_MS = 30_000;
const WALK_DETOUR_FACTOR = 1.3;
const WALK_SPEED_M_PER_MIN = 80;
const LEAVE_BUFFER_MIN = 2;
const MAX_WALK_MIN_FOR_HINTS = 30;

const state = {
  stations: [],
  byId: new Map(),
  favorites: [],
  nearest: null, // { station, walkMinutes }
  lastData: new Map(), // pairKey -> departures payload (for re-render on geolocate)
  expanded: new Set(), // pairKeys showing up to EXPANDED_LIMIT rows (session-only)
  staleness: new Map(), // source -> { stale, asOf }
  dismissedAlerts: new Set(),
  lastFetchMs: 0,
  refreshing: false,
};

const $ = (id) => document.getElementById(id);

/* ---------- time formatting ---------- */

const partsFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: TZ, hour: "numeric", minute: "2-digit", hour12: true,
});
const dateFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: TZ, weekday: "short", month: "short", day: "numeric",
});

function clockShort(value) {
  // "8:19" — board time without AM/PM
  const parts = partsFmt.formatToParts(new Date(value));
  const get = (type) => (parts.find((p) => p.type === type) || {}).value || "";
  return `${get("hour")}:${get("minute")}`;
}

function clockFull(value) {
  return partsFmt.format(new Date(value)); // "9:02 AM"
}

/* ---------- favorites persistence ---------- */

function pairKey(fav) {
  return `${fav.origin}:${fav.destination}`;
}

function loadFavorites() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveFavorites() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.favorites));
  } catch {
    /* private mode etc. — favorites just won't persist */
  }
}

/* ---------- rendering ---------- */

function directionOf(originId, destinationId) {
  const o = state.byId.get(originId);
  const d = state.byId.get(destinationId);
  return o && d && o.order > d.order ? "NB" : "SB";
}

function cardFor(fav) {
  return document.querySelector(`.card[data-pair="${CSS.escape(pairKey(fav))}"]`);
}

function renderCardHead(card, fav) {
  card.dataset.pair = pairKey(fav);
  card.dataset.origin = fav.origin;
  card.dataset.destination = fav.destination;
  card.querySelector(".o").textContent = state.byId.get(fav.origin)?.name ?? fav.origin;
  card.querySelector(".d").textContent = state.byId.get(fav.destination)?.name ?? fav.destination;
  card.querySelector(".dir-tag").textContent = directionOf(fav.origin, fav.destination);
}

function ensureCards() {
  const holder = $("favorites");
  const wanted = new Set(state.favorites.map(pairKey));
  for (const card of [...holder.querySelectorAll(".card")]) {
    if (!wanted.has(card.dataset.pair)) card.remove();
  }
  for (const fav of state.favorites) {
    if (!cardFor(fav)) {
      const card = $("tpl-card").content.firstElementChild.cloneNode(true);
      renderCardHead(card, fav);
      setCardMessage(card, "Loading departures…", "");
      card.classList.add("arriving");
      holder.appendChild(card);
    }
  }
  $("no-favorites").hidden = state.favorites.length > 0;
}

function setCardMessage(card, strong, rest, withRetry = false) {
  const body = card.querySelector(".card-body");
  body.textContent = "";
  const wrap = document.createElement("div");
  wrap.className = "card-empty";
  const p = document.createElement("p");
  const b = document.createElement("strong");
  b.textContent = strong;
  p.append(b);
  if (rest) p.append(document.createElement("br"), rest);
  wrap.append(p);
  if (withRetry) {
    const btn = document.createElement("button");
    btn.className = "btn-retry pressable";
    btn.dataset.action = "retry";
    btn.textContent = "Retry";
    wrap.append(btn);
  }
  body.append(wrap);
}

function typeClass(trainType) {
  switch (trainType) {
    case "Limited": return "type-limited";
    case "Express": return "type-express";
    case "South County": return "type-scc";
    default: return "";
  }
}

function renderCardBody(fav, data) {
  const card = cardFor(fav);
  if (!card) return;
  // the server's direction is authoritative; the local calc only covers the
  // pre-fetch skeleton
  card.querySelector(".dir-tag").textContent = data.direction;

  if (!data.departures.length) {
    setCardMessage(
      card,
      "No upcoming trains for this pair right now.",
      "Weekend and South County service is sparse — this is often normal.",
    );
    return;
  }

  const nearest = state.nearest;
  const showLeaveBy =
    nearest &&
    nearest.station.id === fav.origin &&
    nearest.walkMinutes <= MAX_WALK_MIN_FOR_HINTS;

  const expanded = state.expanded.has(pairKey(fav));
  const shownLimit = expanded ? EXPANDED_LIMIT : COLLAPSED_LIMIT;

  const body = card.querySelector(".card-body");
  body.textContent = "";
  for (const dep of data.departures.slice(0, shownLimit)) {
    const row = $("tpl-dep").content.firstElementChild.cloneNode(true);
    const effective = dep.departure.expected || dep.departure.aimed;

    row.querySelector(".t-big").textContent = clockShort(effective);
    if (dep.status === "late") {
      row.classList.add("is-late");
      const was = row.querySelector(".t-was");
      was.hidden = false;
      was.textContent = clockShort(dep.departure.aimed);
    } else if (dep.status === "scheduled") {
      row.classList.add("is-sched");
    }

    const type = row.querySelector(".type");
    type.textContent = dep.train_type;
    const extra = typeClass(dep.train_type);
    if (extra) type.classList.add(extra);
    row.querySelector(".tno").textContent = dep.train;

    row.querySelector(".dep-arr strong").textContent = dep.arrival
      ? clockFull(dep.arrival.expected || dep.arrival.aimed)
      : "—";

    const badge = row.querySelector(".badge");
    if (dep.status === "late") {
      badge.textContent = `+${Math.round(dep.delay_seconds / 60)} min`;
      badge.classList.add("b-late");
    } else if (dep.status === "on_time") {
      badge.textContent = "On time";
      badge.classList.add("b-ok");
    } else {
      badge.textContent = "Scheduled";
      badge.classList.add("b-sched");
    }

    if (showLeaveBy) {
      const leave = row.querySelector(".leave");
      const leaveMs =
        Date.parse(effective) - (nearest.walkMinutes + LEAVE_BUFFER_MIN) * 60_000;
      leave.hidden = false;
      leave.querySelector("strong").textContent = clockShort(leaveMs);
    }

    body.append(row);
  }

  const foot = document.createElement("div");
  foot.className = "card-foot";
  if (data.departures.length < shownLimit) {
    const note = document.createElement("p");
    note.className = "foot-note";
    note.textContent = "That's every upcoming train in the live feed right now.";
    foot.append(note);
  }
  if (!expanded && data.departures.length >= COLLAPSED_LIMIT) {
    foot.append(makeFootButton("expand-card", "Show more"));
  } else if (expanded) {
    foot.append(makeFootButton("collapse-card", "Show fewer"));
  }
  if (foot.childNodes.length) body.append(foot);
}

function makeFootButton(action, label) {
  const btn = document.createElement("button");
  btn.className = "btn-foot pressable";
  btn.dataset.action = action;
  btn.textContent = label;
  return btn;
}

function renderAlerts(alerts) {
  const holder = $("alerts");
  holder.textContent = "";
  for (const alert of alerts) {
    if (state.dismissedAlerts.has(alert.id)) continue;
    const node = $("tpl-alert").content.firstElementChild.cloneNode(true);
    node.dataset.alertId = alert.id;
    node.querySelector(".alert-header").textContent = alert.header;
    node.querySelector(".alert-desc").textContent = alert.description;
    holder.append(node);
  }
}

function renderChip() {
  if (!state.nearest) return;
  $("chip-row").hidden = false;
  $("chip-station").textContent = state.nearest.station.name;
  $("chip-walk").textContent = `~${state.nearest.walkMinutes} min walk`;
}

function renderUpdated() {
  let newest = 0;
  for (const { asOf } of state.staleness.values()) {
    newest = Math.max(newest, Date.parse(asOf) || 0);
  }
  const label = $("updated");
  if (!newest) {
    label.textContent = "";
    return;
  }
  const ageS = (Date.now() - newest) / 1000;
  label.textContent = ageS < 45 ? "Updated just now" : `Updated ${Math.round(ageS / 60)}m ago`;
}

function renderStalePill() {
  const staleEntries = [...state.staleness.values()].filter((s) => s.stale);
  const pill = $("stale-pill");
  pill.hidden = staleEntries.length === 0;
  if (staleEntries.length) {
    const oldest = staleEntries
      .map((s) => Date.parse(s.asOf) || 0)
      .reduce((a, b) => Math.min(a, b), Infinity);
    $("stale-text").textContent = `Live data unavailable — showing ${clockFull(oldest)} data`;
  }
}

/* ---------- data fetching ---------- */

async function fetchPair(fav) {
  const key = pairKey(fav);
  const limit = state.expanded.has(key) ? EXPANDED_LIMIT : COLLAPSED_LIMIT;
  const params = new URLSearchParams({
    origin: fav.origin,
    destination: fav.destination,
    limit: String(limit),
  });
  try {
    const resp = await fetch(`/api/departures?${params}`, { cache: "no-store" });
    if (!resp.ok) throw new Error(`http ${resp.status}`);
    const data = await resp.json();
    state.lastData.set(key, data);
    state.staleness.set(key, { stale: data.stale, asOf: data.as_of });
    renderCardBody(fav, data);
  } catch {
    state.staleness.delete(key);
    const card = cardFor(fav);
    if (card) setCardMessage(card, "Can't reach the server.", "Check your connection and retry.", true);
  }
}

async function fetchAlerts() {
  try {
    const resp = await fetch("/api/alerts", { cache: "no-store" });
    if (!resp.ok) throw new Error(`http ${resp.status}`);
    const data = await resp.json();
    state.staleness.set("alerts", { stale: data.stale, asOf: data.as_of });
    renderAlerts(data.alerts);
  } catch {
    /* alerts are best-effort; departures errors already surface */
  }
}

async function refresh() {
  if (state.refreshing || !state.stations.length) return;
  state.refreshing = true;
  const btn = document.querySelector('[data-action="refresh"]');
  btn.classList.add("spinning");
  try {
    await Promise.allSettled([...state.favorites.map(fetchPair), fetchAlerts()]);
    state.lastFetchMs = Date.now();
    renderUpdated();
    renderStalePill();
  } finally {
    state.refreshing = false;
    btn.classList.remove("spinning");
  }
}

/* ---------- geolocation ---------- */

function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(lat2 - lat1);
  const dLon = rad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function locate() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      let best = null;
      let bestMeters = Infinity;
      for (const s of state.stations) {
        const m = haversineMeters(pos.coords.latitude, pos.coords.longitude, s.lat, s.lon);
        if (m < bestMeters) {
          bestMeters = m;
          best = s;
        }
      }
      if (!best) return;
      state.nearest = {
        station: best,
        walkMinutes: Math.ceil((bestMeters * WALK_DETOUR_FACTOR) / WALK_SPEED_M_PER_MIN),
      };
      renderChip();
      // re-render cached cards so leave-by hints appear without a refetch
      for (const fav of state.favorites) {
        const data = state.lastData.get(pairKey(fav));
        if (data) renderCardBody(fav, data);
      }
    },
    () => { /* denied/unavailable — chip stays hidden, no hints */ },
    { maximumAge: 120_000, timeout: 8_000 },
  );
}

/* ---------- actions (single delegated listener, no inline onclick) ---------- */

function shakeAddRow() {
  const row = $("add-row");
  row.classList.remove("shake");
  void row.offsetWidth;
  row.classList.add("shake");
}

function favFromCard(el) {
  const card = el.closest(".card");
  return {
    card,
    fav: state.favorites.find((f) => pairKey(f) === card.dataset.pair),
  };
}

function dropPairState(key) {
  state.lastData.delete(key);
  state.staleness.delete(key);
  state.expanded.delete(key);
  renderStalePill();
}

document.body.addEventListener("click", (e) => {
  const el = e.target.closest("[data-action]");
  if (!el) return;

  switch (el.dataset.action) {
    case "refresh": {
      refresh();
      break;
    }
    case "dismiss-alert": {
      const banner = el.closest(".alert");
      state.dismissedAlerts.add(banner.dataset.alertId);
      banner.remove();
      break;
    }
    case "swap-add": {
      const a = $("sel-origin").value;
      $("sel-origin").value = $("sel-dest").value;
      $("sel-dest").value = a;
      break;
    }
    case "add-favorite": {
      const fav = { origin: $("sel-origin").value, destination: $("sel-dest").value };
      const exists = state.favorites.some((f) => pairKey(f) === pairKey(fav));
      if (fav.origin === fav.destination || exists || state.favorites.length >= MAX_FAVORITES) {
        shakeAddRow();
        return;
      }
      state.favorites.push(fav);
      saveFavorites();
      ensureCards();
      fetchPair(fav);
      break;
    }
    case "swap-card": {
      const { card, fav } = favFromCard(el);
      if (!fav) return;
      dropPairState(card.dataset.pair);
      [fav.origin, fav.destination] = [fav.destination, fav.origin];
      saveFavorites();
      renderCardHead(card, fav);
      setCardMessage(card, "Loading departures…", "");
      fetchPair(fav);
      break;
    }
    case "remove-card": {
      const { card, fav } = favFromCard(el);
      if (fav) {
        state.favorites = state.favorites.filter((f) => pairKey(f) !== pairKey(fav));
        saveFavorites();
        dropPairState(pairKey(fav));
      }
      card.classList.add("leaving");
      setTimeout(() => {
        card.remove();
        $("no-favorites").hidden = state.favorites.length > 0;
      }, 200);
      break;
    }
    case "retry": {
      const { card, fav } = favFromCard(el);
      if (!fav) return;
      setCardMessage(card, "Loading departures…", "");
      fetchPair(fav);
      break;
    }
    case "expand-card": {
      const { card, fav } = favFromCard(el);
      if (!fav) return;
      state.expanded.add(card.dataset.pair);
      fetchPair(fav); // refetch at the higher limit; rows update in place
      break;
    }
    case "collapse-card": {
      const { card, fav } = favFromCard(el);
      if (!fav) return;
      state.expanded.delete(card.dataset.pair);
      const cached = state.lastData.get(card.dataset.pair);
      if (cached) renderCardBody(fav, cached);
      break;
    }
  }
});

/* ---------- startup ---------- */

async function init() {
  $("today").textContent = dateFmt.format(new Date());
  $("footer-note").textContent = "Times shown in Pacific Time · realtime data from 511.org";

  let stationsPayload;
  try {
    const resp = await fetch("/api/stations", { cache: "no-store" });
    stationsPayload = await resp.json();
  } catch {
    $("no-favorites").hidden = false;
    $("no-favorites").textContent = "Can't reach the server — reload to retry.";
    return;
  }

  state.stations = stationsPayload.stations;
  state.byId = new Map(state.stations.map((s) => [s.id, s]));

  const selOrigin = $("sel-origin");
  const selDest = $("sel-dest");
  for (const s of state.stations) {
    selOrigin.add(new Option(s.name, s.id));
    selDest.add(new Option(s.name, s.id));
  }
  if (state.byId.has("san_carlos")) selOrigin.value = "san_carlos";
  if (state.byId.has("san_francisco")) selDest.value = "san_francisco";

  state.favorites = loadFavorites()
    .filter((f) => f && state.byId.has(f.origin) && state.byId.has(f.destination))
    .slice(0, MAX_FAVORITES);
  saveFavorites();
  ensureCards();

  locate();
  refresh();

  setInterval(() => {
    if (!document.hidden) refresh();
  }, REFRESH_INTERVAL_MS);

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && Date.now() - state.lastFetchMs > VISIBILITY_REFRESH_AFTER_MS) {
      refresh();
    }
  });
}

init();
