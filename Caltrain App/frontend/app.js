/* Bay Rail (Caltrain + BART) commute helper — vanilla JS, no build step.
   All dynamic text is set via textContent (never innerHTML with API data).
   All times render in America/Los_Angeles — the server runs UTC. */
"use strict";

const TZ = "America/Los_Angeles";
const STORAGE_KEY = "transit:favorites:v2";
const LEGACY_STORAGE_KEY = "caltrain:favorites:v1"; // migrated, left in place (§9.1)
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
  stations: [], // Caltrain, north→south (line order)
  bartStations: [], // BART, alphabetical (a branching network has no line order)
  byAgency: { ct: new Map(), ba: new Map() },
  favorites: [], // [{ agency, origin, destination }]
  nearest: null, // { station (carries .agency), walkMinutes }
  lastData: new Map(), // pairKey -> departures payload (for re-render on geolocate)
  expanded: new Set(), // pairKeys showing up to EXPANDED_LIMIT rows (session-only)
  staleness: new Map(), // source -> { stale, asOf }
  lastAlerts: null, // latest alerts payload (re-applied when cards change)
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
  return `${fav.agency}:${fav.origin}:${fav.destination}`;
}

function loadFavorites() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (Array.isArray(parsed)) return parsed;
  } catch {
    /* fall through to migration */
  }
  // one-time v1 → v2 migration; v1 stays behind for rollback safety
  try {
    const legacy = JSON.parse(localStorage.getItem(LEGACY_STORAGE_KEY));
    if (Array.isArray(legacy)) {
      return legacy.map((fav) => ({ agency: "ct", ...fav }));
    }
  } catch {
    /* corrupt legacy data — start fresh */
  }
  return [];
}

function saveFavorites() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.favorites));
  } catch {
    /* private mode etc. — favorites just won't persist */
  }
}

/* ---------- rendering ---------- */

function stationName(agency, id) {
  return state.byAgency[agency]?.get(id)?.name ?? id;
}

function directionOf(originId, destinationId) {
  const o = state.byAgency.ct.get(originId);
  const d = state.byAgency.ct.get(destinationId);
  return o && d && o.order > d.order ? "NB" : "SB";
}

function cardFor(fav) {
  return document.querySelector(`.card[data-pair="${CSS.escape(pairKey(fav))}"]`);
}

function endName(fav, key) {
  // xa favorites store agency-prefixed ends ("ct:san_carlos" — SPEC-V2 §7.6)
  return fav.agency === "xa"
    ? stationName(agencyOf(fav[key]), idOf(fav[key]))
    : stationName(fav.agency, fav[key]);
}

function renderCardHead(card, fav) {
  card.dataset.pair = pairKey(fav);
  card.dataset.agency = fav.agency;
  card.dataset.origin = fav.origin;
  card.dataset.destination = fav.destination;
  card.querySelector(".o").textContent = endName(fav, "origin");
  card.querySelector(".d").textContent = endName(fav, "destination");
  // the dir-tag slot carries the agency for BART (no NB/SB on a network) and
  // the leg order for cross-agency pairs
  card.querySelector(".dir-tag").textContent =
    fav.agency === "ba" ? "BART"
    : fav.agency === "xa" ? (agencyOf(fav.origin) === "ct" ? "CT ▸ BART" : "BART ▸ CT")
    : directionOf(fav.origin, fav.destination);
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
  if (state.lastAlerts) renderAlerts(state.lastAlerts); // re-apply card chips
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

function paintLinePill(el, name, colorHex) {
  el.textContent = name;
  if (/^#[0-9a-fA-F]{6}$/.test(colorHex || "")) {
    el.style.color = colorHex;
    el.style.background = colorHex + "1f"; // ≈12% tint, matches the mockup pills
  }
}

function renderDepInfo(row, dep) {
  const line = row.querySelector(".dep-line");
  const type = row.querySelector(".type");
  const tno = row.querySelector(".tno");

  if (dep.legs) {
    // transfer itinerary: leg pills joined by ▸, then the change-at line —
    // no headsign (the card title already names the destination). Legs are
    // agency-tagged on xa itineraries: ct legs render the type pill, ba legs
    // the line-color pill (SPEC-V2 §7.5).
    line.textContent = "";
    dep.legs.forEach((leg, i) => {
      if (i > 0) {
        const arrow = document.createElement("span");
        arrow.className = "leg-arrow";
        arrow.textContent = "▸";
        line.append(arrow);
      }
      const pill = document.createElement("span");
      pill.className = "type";
      if (leg.agency === "ct") {
        pill.textContent = leg.train_type;
        const extra = typeClass(leg.train_type);
        if (extra) pill.classList.add(extra);
      } else {
        paintLinePill(pill, leg.line, leg.line_color);
      }
      line.append(pill);
    });
    const xfer = row.querySelector(".dep-xfer");
    xfer.hidden = false;
    xfer.textContent = "change at ";
    dep.transfers.forEach((transfer, i) => {
      if (i > 0) xfer.append(", then ");
      const name = document.createElement("strong");
      name.textContent = transfer.station_name;
      xfer.append(name, ` · ${transfer.wait_minutes} min wait`);
      if (transfer.at_risk) {
        const risk = document.createElement("span");
        risk.className = "xfer-risk";
        risk.textContent = " · tight connection";
        xfer.append(risk);
      }
    });
  } else if (dep.line) {
    // BART direct: line pill + headsign replace type pill + train number
    paintLinePill(type, dep.line, dep.line_color);
    tno.textContent = dep.headsign;
  } else {
    type.textContent = dep.train_type;
    const extra = typeClass(dep.train_type);
    if (extra) type.classList.add(extra);
    tno.textContent = dep.train;
  }
}

function renderCardBody(fav, data) {
  const card = cardFor(fav);
  if (!card) return;
  if (data.agency === "ct") {
    // the server's direction is authoritative; the local calc only covers
    // the pre-fetch skeleton (BART and xa cards keep their static tags)
    card.querySelector(".dir-tag").textContent = data.direction;
  }

  if (!data.departures.length) {
    // static copy only (SPEC-V2 §4.6) — never a computed "first train at HH:MM"
    setCardMessage(
      card,
      "No upcoming trains for this pair right now.",
      data.agency === "ba"
        ? "BART runs roughly 4 AM (6 AM Saturday, 8 AM Sunday) to midnight — overnight emptiness is normal."
        : data.agency === "xa"
          ? "Cross-agency trips connect at Millbrae, and Caltrain's live feed only sees ~90 minutes ahead — itineraries appear as the connection gets closer."
          : "Caltrain's first weekday trains leave around 4–5 AM; weekend and South County service is sparse — this is often normal.",
    );
    return;
  }

  const nearest = state.nearest;
  const originEnd = fav.agency === "xa"
    ? { agency: agencyOf(fav.origin), id: idOf(fav.origin) }
    : { agency: fav.agency, id: fav.origin };
  const showLeaveBy =
    nearest &&
    nearest.station.agency === originEnd.agency &&
    nearest.station.id === originEnd.id &&
    nearest.walkMinutes <= MAX_WALK_MIN_FOR_HINTS;

  const expanded = state.expanded.has(pairKey(fav));
  const shownLimit = expanded ? EXPANDED_LIMIT : COLLAPSED_LIMIT;

  // Canceled rows are additive to the limit (SPEC-V2 §5.4): cap live rows at
  // shownLimit and let in-window canceled rows ride along — a canceled train
  // must never push a live train off the board. Once the live cap is hit,
  // later canceled rows are outside the shown window too.
  const shown = [];
  let liveCount = 0;
  for (const dep of data.departures) {
    if (liveCount >= shownLimit) break;
    if (dep.status !== "canceled") liveCount++;
    shown.push(dep);
  }

  const body = card.querySelector(".card-body");
  body.textContent = "";
  for (const dep of shown) {
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
    } else if (dep.status === "canceled") {
      row.classList.add("is-canceled");
    }

    renderDepInfo(row, dep);

    if (dep.last_train) {
      const tag = document.createElement("span");
      tag.className = "tag-last";
      tag.textContent = "Last train tonight";
      row.querySelector(".dep-arr").before(tag);
    }

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
    } else if (dep.status === "canceled") {
      badge.textContent = "Canceled";
      badge.classList.add("b-canceled");
    } else {
      badge.textContent = "Scheduled";
      badge.classList.add("b-sched");
    }

    if (showLeaveBy && dep.status !== "canceled") {
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
  const liveTotal = data.departures.filter((dep) => dep.status !== "canceled").length;
  if (liveTotal < shownLimit) {
    const note = document.createElement("p");
    note.className = "foot-note";
    note.textContent = "That's every upcoming train in the live feed right now.";
    foot.append(note);
  }
  if (!expanded && liveTotal >= COLLAPSED_LIMIT) {
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

/* per-pair alert linkage (SPEC-V2 §3): a stop-scoped alert chips every
   favorite card whose match set intersects its stops, and is then suppressed
   from the global banner — the chip is the better surface. */

function matchSet(fav) {
  const codes = new Set();
  const addCt = (id) => {
    const s = state.byAgency.ct.get(id);
    if (s) { codes.add(s.stop_nb); codes.add(s.stop_sb); }
  };
  const addBa = (id) => {
    const s = state.byAgency.ba.get(id);
    if (s) codes.add(s.abbr);
  };
  if (fav.agency === "ct") {
    addCt(fav.origin); addCt(fav.destination);
  } else if (fav.agency === "ba") {
    addBa(fav.origin); addBa(fav.destination);
  } else {
    // xa: both ends plus the Millbrae transfer codes — the rider passes
    // through Millbrae on every cross-agency trip (§3.3)
    for (const value of [fav.origin, fav.destination]) {
      (agencyOf(value) === "ct" ? addCt : addBa)(idOf(value));
    }
    addCt("millbrae");
    codes.add("MLBR");
  }
  codes.delete(undefined);
  return codes;
}

function stationNameForCode(code) {
  for (const s of state.stations) {
    if (s.stop_nb === code || s.stop_sb === code) return s.name;
  }
  const bart = state.bartStations.find((s) => s.abbr === code);
  return bart ? bart.name : code;
}

function makeCardAlert(alert, matchedCodes) {
  const node = $("tpl-card-alert").content.firstElementChild.cloneNode(true);
  const lead = node.querySelector(".chip-lead");
  const strong = node.querySelector("strong");
  if (alert.type === "elevator" && alert.agency === "ba") {
    // the BART advisory is one shared prose blob — compose a per-card chip
    const names = [...new Set(matchedCodes.map(stationNameForCode))];
    lead.textContent = "Elevator out at ";
    strong.textContent = names.join(", ");
  } else {
    lead.textContent = alert.header; // 511 headers are per-outage prose
  }
  return node;
}

function renderAlerts(alerts) {
  state.lastAlerts = alerts;
  const holder = $("alerts");
  holder.textContent = "";
  const chipped = new Set();

  for (const card of document.querySelectorAll("#favorites .card")) {
    const chipHolder = card.querySelector(".card-alerts");
    if (!chipHolder) continue;
    chipHolder.textContent = "";
    const fav = state.favorites.find((f) => pairKey(f) === card.dataset.pair);
    if (!fav) continue;
    const codes = matchSet(fav);
    for (const alert of alerts) {
      const matched = (alert.stops || []).filter((code) => codes.has(code));
      if (!matched.length) continue;
      chipped.add(alert.id);
      chipHolder.append(makeCardAlert(alert, matched));
    }
  }

  for (const alert of alerts) {
    if (state.dismissedAlerts.has(alert.id) || chipped.has(alert.id)) continue;
    const node = $("tpl-alert").content.firstElementChild.cloneNode(true);
    node.dataset.alertId = alert.id;
    if (alert.agency === "ba") {
      const tag = node.querySelector(".src-tag");
      tag.hidden = false;
      tag.textContent = "BART"; // Caltrain alerts stay untagged, as today
    }
    if (alert.type === "elevator") {
      const tag = document.createElement("span");
      tag.className = "src-tag";
      tag.textContent = "ELEVATOR"; // beside the agency tag (SPEC-V2 §6.3)
      node.querySelector(".alert-header").before(tag);
    }
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
    agency: fav.agency,
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
    const resp = await fetch("/api/alerts?agency=all", { cache: "no-store" });
    if (!resp.ok) throw new Error(`http ${resp.status}`);
    const data = await resp.json();
    state.staleness.set("alerts", { stale: data.stale, asOf: data.as_of });
    renderAlerts(data.alerts);
  } catch {
    /* alerts are best-effort; departures errors already surface */
  }
}

async function refresh() {
  if (state.refreshing || !allStations().length) return;
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

function allStations() {
  // nearest-station search runs over the union of both agencies (§9.5)
  return [
    ...state.stations.map((s) => ({ ...s, agency: "ct" })),
    ...state.bartStations.map((s) => ({ ...s, agency: "ba" })),
  ];
}

function locate() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      let best = null;
      let bestMeters = Infinity;
      for (const s of allStations()) {
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
      // both selects always carry both groups (SPEC-V2 §7.6) — plain swap
      const a = $("sel-origin").value;
      $("sel-origin").value = $("sel-dest").value;
      $("sel-dest").value = a;
      break;
    }
    case "add-favorite": {
      const originValue = $("sel-origin").value;
      const destValue = $("sel-dest").value;
      const mixed = agencyOf(originValue) !== agencyOf(destValue);
      // a Millbrae endpoint on a mixed pair is a single-agency pair in
      // disguise (SPEC-V2 §7.2) — same shake as the other violations
      const millbraeEnd = idOf(originValue) === "millbrae" || idOf(destValue) === "millbrae";
      const fav = mixed
        ? { agency: "xa", origin: originValue, destination: destValue }
        : { agency: agencyOf(originValue), origin: idOf(originValue), destination: idOf(destValue) };
      const exists = state.favorites.some((f) => pairKey(f) === pairKey(fav));
      if (
        originValue === destValue || (mixed && millbraeEnd) ||
        exists || state.favorites.length >= MAX_FAVORITES
      ) {
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
        // an alert chipped only on this card must return to the banner —
        // visibility is never lost (SPEC-V2 §3.3)
        if (state.lastAlerts) renderAlerts(state.lastAlerts);
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

/* ---------- unified station pickers (§9.4) ---------- */

// Option values carry "agency:id" — picking a station IS picking the agency,
// so invalid mixed pairs are unpickable rather than validated after the fact.
const agencyOf = (value) => value.split(":", 1)[0];
const idOf = (value) => value.slice(value.indexOf(":") + 1);

function fillSelect(sel, agencyFilter) {
  const previous = sel.value;
  const groups = [
    ["ct", "Caltrain", state.stations],
    ["ba", "BART", state.bartStations],
  ];
  sel.replaceChildren(); // not `length = 0`, which leaves empty optgroups behind
  for (const [agency, label, list] of groups) {
    if (agencyFilter && agency !== agencyFilter) continue;
    const group = document.createElement("optgroup");
    group.label = label;
    for (const s of list) group.appendChild(new Option(s.name, `${agency}:${s.id}`));
    sel.appendChild(group);
  }
  if ([...sel.options].some((option) => option.value === previous)) sel.value = previous;
}

/* ---------- startup ---------- */

async function init() {
  $("today").textContent = dateFmt.format(new Date());
  $("footer-note").textContent =
    "Times shown in Pacific Time · realtime data from 511.org and bart.gov";

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
  state.bartStations = stationsPayload.bart_stations ?? [];
  state.byAgency.ct = new Map(state.stations.map((s) => [s.id, s]));
  state.byAgency.ba = new Map(state.bartStations.map((s) => [s.id, s]));

  const selOrigin = $("sel-origin");
  const selDest = $("sel-dest");
  // v2 (SPEC-V2 §7.6): no destination narrowing — both selects always list
  // both agency groups; ends in different agencies make a cross-agency pair
  fillSelect(selOrigin, null);
  if (state.byAgency.ct.has("san_carlos")) selOrigin.value = "ct:san_carlos";
  fillSelect(selDest, null);
  if (state.byAgency.ct.has("san_francisco")) selDest.value = "ct:san_francisco";

  const validEnd = (agency, id) => state.byAgency[agency]?.has(id);
  const validFav = (f) => {
    if (!f || !f.agency) return false;
    if (f.agency === "xa") {
      const ends = [f.origin, f.destination].map((v) => [agencyOf(v || ""), idOf(v || "")]);
      return ends[0][0] !== ends[1][0]
        && ends.every(([agency, id]) => validEnd(agency, id))
        && !ends.some(([, id]) => id === "millbrae"); // degenerate pair (§7.2)
    }
    return validEnd(f.agency, f.origin) && validEnd(f.agency, f.destination);
  };
  state.favorites = loadFavorites()
    .map((f) => f && { agency: "ct", ...f }) // tolerate agencyless v1-shaped entries
    .filter(validFav)
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
