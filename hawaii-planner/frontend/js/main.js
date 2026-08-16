// Boot: token capture -> identity -> bootstrap fetch -> render + polling.
import { api, captureTokenFromUrl } from "./api.js";
import { youSheet } from "./sheets.js";
import {
  markSeen,
  onRender,
  refresh,
  render,
  saveMember,
  snapshotSeen,
  startPolling,
  state,
  storedMember,
  tabHasNew,
} from "./state.js";
import { avatar, closeSheet, h, toast } from "./ui.js";
import { renderEats } from "./views/eats.js";
import { renderIdeas } from "./views/ideas.js";
import { renderSchedule } from "./views/schedule.js";

const TABS = [
  { id: "schedule", icon: "🗓", label: "Itinerary", hash: "#/day" },
  { id: "ideas", icon: "🌴", label: "Ideas", hash: "#/ideas" },
  { id: "eats", icon: "🍽", label: "Food", hash: "#/eats" },
];

function applyHash() {
  const hash = location.hash;
  if (hash.startsWith("#/day")) {
    state.tab = "schedule";
    state.dayId = hash.slice("#/day/".length) || state.dayId;
  } else if (hash === "#/ideas") state.tab = "ideas";
  else if (hash === "#/eats") state.tab = "eats";
}

function setTab(tabId) {
  state.tab = tabId;
  state.reorderMode = false;
  location.hash = tabId === "schedule" ? (state.dayId ? `#/day/${state.dayId}` : "#/day") : `#/${tabId}`;
  render();
}

function tabButton(tab) {
  const showDot = tab.id !== state.tab && (tab.id === "ideas" || tab.id === "eats") && tabHasNew(tab.id);
  return h(
    "button",
    {
      type: "button",
      className: `tab ${state.tab === tab.id ? "active" : ""}`,
      onclick: () => setTab(tab.id),
    },
    h("span", { className: "tab-icon", text: tab.icon }),
    h("span", { text: tab.label }),
    showDot ? h("span", { className: "dot" }) : null
  );
}

function renderChrome() {
  const tabbar = document.getElementById("tabbar");
  const topnav = document.getElementById("topnav");
  tabbar.replaceChildren(...TABS.map(tabButton));
  topnav.replaceChildren(...TABS.map(tabButton));

  const chip = document.getElementById("you-chip");
  chip.replaceChildren();
  if (state.member) {
    chip.append(avatar(state.member), state.member.name);
  } else {
    chip.append("Who are you?");
  }
}

function renderView() {
  const root = document.getElementById("view");
  root.className = "view";
  root.replaceChildren();
  if (!state.data) return;
  if (state.tab === "ideas") {
    renderIdeas(root);
    markSeen("ideas");
  } else if (state.tab === "eats") {
    renderEats(root);
    markSeen("eats");
  } else {
    renderSchedule(root);
  }
}

onRender(() => {
  renderChrome();
  renderView();
});

// ── Name picker ────────────────────────────────────────────
function showPicker() {
  const rootEl = document.getElementById("picker-root");
  const list = h("div", {});
  for (const member of state.data.members) {
    list.append(
      h("button", {
        className: "name-btn",
        type: "button",
        text: member.name,
        onclick: () => pick(member),
      })
    );
  }
  const otherName = h("input", { placeholder: "Your name", maxLength: 40, style: { marginBottom: "10px" } });
  const otherWrap = h(
    "div",
    { className: "hidden" },
    otherName,
    h("button", {
      className: "name-btn",
      type: "button",
      text: "Join the trip",
      onclick: async () => {
        const name = otherName.value.trim();
        if (!name) return;
        const payload = await api("/api/members", { method: "POST", body: { name } });
        pick(payload.member);
      },
    })
  );

  function pick(member) {
    saveMember(member);
    rootEl.replaceChildren();
    toast(`Aloha, ${member.name}! Your name is remembered on this phone 🌺`);
    render();
  }

  rootEl.replaceChildren(
    h(
      "div",
      { className: "picker" },
      h(
        "div",
        { className: "picker-card" },
        h("div", { className: "flower", text: "🌺" }),
        h("h1", { text: "Aloha!" }),
        h("p", { className: "sub", text: "Oahu · Aug 26–31 — who's this? (so we know who added and voted on things)" }),
        list,
        h("button", {
          className: "btn subtle",
          type: "button",
          text: "+ I'm someone else",
          onclick: () => otherWrap.classList.remove("hidden"),
        }),
        otherWrap
      )
    )
  );
}

// ── Global delegation for static-HTML actions ──────────────
document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  if (action === "sheet-close") closeSheet();
  if (action === "open-you" && state.data) {
    youSheet(() => showPicker());
  }
});

window.addEventListener("hashchange", () => {
  applyHash();
  render();
});

// ── Boot ───────────────────────────────────────────────────
async function boot() {
  captureTokenFromUrl();
  snapshotSeen();
  state.member = storedMember();
  applyHash();
  try {
    await refresh();
  } catch {
    document.getElementById("view").replaceChildren(
      h(
        "div",
        { className: "empty", style: { margin: "40px 14px" } },
        h("p", { text: "Couldn't load the trip — make sure you opened the full shared link (it contains the key)." })
      )
    );
    return;
  }
  // Validate the remembered identity against the live roster.
  if (state.member && !state.data.members.some((m) => m.id === state.member.id)) {
    state.member = null;
  }
  if (!state.member) showPicker();
  startPolling();
}

boot();
