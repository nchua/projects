// Shared UI primitives: DOM builder, sheets, toasts, formatting, region colors.

export const REGION_COLORS = {
  WAI: "#F76F63",
  HNL: "#E8A13C",
  PRL: "#5C7CFA",
  EAST: "#2F9E44",
  WINDS: "#22B8CF",
  WINDN: "#12B886",
  NS: "#1864AB",
  CEN: "#C9A227",
  KOOL: "#C2255C",
};

export const HOME_NAME = "Aston Waikiki Beach Tower";

// h("div", {className, dataset:{action}, text, html:NEVER}, ...children)
// All dynamic strings go through .textContent — never innerHTML.
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null) continue;
    if (key === "text") el.textContent = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key === "style") Object.assign(el.style, value);
    else if (key.includes("-")) el.setAttribute(key, value);
    else el[key] = value;
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(child));
  }
  return el;
}

export function fmtTime(hhmm) {
  if (!hhmm) return "";
  const [h24, m] = hhmm.split(":").map(Number);
  const suffix = h24 >= 12 ? "PM" : "AM";
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
  return `${h12}:${String(m).padStart(2, "0")} ${suffix}`;
}

export function fmtDur(minutes) {
  if (minutes == null) return "";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

const WEEKDAY_NAMES = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
export function fmtClosedDays(tokens) {
  return (tokens || []).map((token) => WEEKDAY_NAMES[token] || token).join(", ");
}

export function dayDate(day) {
  return day.date ? new Date(day.date + "T12:00:00") : null;
}

// Indexed by Date.getDay() (Sunday = 0) to match the backend's closed_days tokens.
const WEEKDAY_TOKENS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
export function dayWeekdayToken(day) {
  const date = dayDate(day);
  return date ? WEEKDAY_TOKENS[date.getDay()] : null;
}

export function dayShort(day, index) {
  const date = dayDate(day);
  if (!date) return { dow: `Day ${index + 1}`, sub: "" };
  return {
    dow: date.toLocaleDateString("en-US", { weekday: "short" }),
    sub: date.toLocaleDateString("en-US", { month: "numeric", day: "numeric" }),
  };
}

export function dayTitle(day, index) {
  const date = dayDate(day);
  const base = date
    ? date.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })
    : `Day ${index + 1}`;
  return day.label ? `${base} · ${day.label}` : base;
}

export function regionName(regions, regionId) {
  return regions.find((region) => region.id === regionId)?.name ?? regionId;
}

export function regionChip(regions, regionId) {
  return h(
    "span",
    { className: "chip" },
    h("span", { className: "swatch", style: { background: REGION_COLORS[regionId] || "#999" } }),
    regionName(regions, regionId)
  );
}

// The plain filter/sort chip used by the board headers.
export function filterChip(label, active, onClick) {
  return h("button", {
    type: "button",
    className: `chip ${active ? "active" : ""}`,
    text: label,
    onclick: onClick,
  });
}

export function avatar(member) {
  return h("span", {
    className: "avatar",
    text: member.name.slice(0, 1).toUpperCase(),
    style: { background: member.color },
  });
}

export function mapsDirUrl(origin, destination, destMapsUrl) {
  if (destMapsUrl) return destMapsUrl;
  const params = new URLSearchParams({
    api: "1",
    origin: `${origin}, Oahu, HI`,
    destination: `${destination}, Oahu, HI`,
  });
  return `https://www.google.com/maps/dir/?${params}`;
}

export function yelpUrl(idea) {
  if (idea.yelp_url) return idea.yelp_url;
  const params = new URLSearchParams({ find_desc: idea.title, find_loc: "Honolulu, HI" });
  return `https://www.yelp.com/search?${params}`;
}

// ── Toasts ──────────────────────────────────────────────────
export function toast(message, kind = "info") {
  const root = document.getElementById("toast-root");
  const el = h("div", { className: `toast ${kind === "error" ? "error" : ""}`, text: message });
  root.append(el);
  setTimeout(() => el.remove(), 3200);
}

// ── Sheets ──────────────────────────────────────────────────
let activeSheet = null;

export function closeSheet() {
  if (activeSheet) {
    activeSheet.remove();
    activeSheet = null;
  }
}

export function openSheet(title, ...content) {
  closeSheet();
  const sheet = h(
    "div",
    { className: "sheet" },
    h(
      "div",
      { className: "sheet-head" },
      h("h3", { text: title }),
      h("button", { className: "sheet-close", text: "✕", type: "button", dataset: { action: "sheet-close" } })
    ),
    ...content
  );
  const scrim = h("div", { className: "scrim" }, sheet);
  scrim.addEventListener("click", (event) => {
    if (event.target === scrim) closeSheet();
  });
  activeSheet = scrim;
  document.getElementById("sheet-root").append(scrim);
  return sheet;
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeSheet();
});

// ── Form field helpers ──────────────────────────────────────
export function field(labelText, control) {
  return h("div", { className: "field" }, h("label", { text: labelText }), control);
}

export function stepper({ value, min = 15, max = 720, step = 15, format = fmtDur, onChange }) {
  let current = value;
  const display = h("span", { className: "val", text: format(current) });
  const make = (delta, label) =>
    h("button", {
      type: "button",
      text: label,
      onclick: () => {
        current = Math.min(max, Math.max(min, current + delta));
        display.textContent = format(current);
        onChange(current);
      },
    });
  return h("div", { className: "stepper" }, make(-step, "−"), display, make(step, "+"));
}

export function regionChipRow(regions, selectedId, onPick) {
  const row = h("div", { className: "chip-row" });
  for (const region of regions) {
    const chip = h(
      "button",
      {
        type: "button",
        className: `chip ${region.id === selectedId ? "active" : ""}`,
        onclick: () => {
          row.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
          chip.classList.add("active");
          onPick(region.id);
        },
      },
      h("span", { className: "swatch", style: { background: REGION_COLORS[region.id] || "#999" } }),
      region.name
    );
    row.append(chip);
  }
  return row;
}
