// Ideas pool: region-grouped activity cards, cluster banners, filters.
import { api } from "../api.js";
import { addIdeaSheet, addIdeaToDay, dayPickerSheet, ideaDetailSheet } from "../sheets.js";
import { applyDay, render, state } from "../state.js";
import { REGION_COLORS, filterChip, fmtDur, h, regionName, toast } from "../ui.js";
import {
  CLUSTER_MIN,
  creditLine,
  newPill,
  reactionPill,
  scheduledBadge,
  unscheduledActivitiesByRegion,
} from "./shared.js";

function filterRow(current, onPick) {
  const row = h("div", { className: "filter-row" });
  const chip = (id, label) => filterChip(label, current === id, () => onPick(id));
  row.append(chip(null, "All"));
  for (const region of state.data.regions) {
    row.append(chip(region.id, region.name));
  }
  return row;
}

function clusterBanners() {
  const banners = [];
  for (const [regionId, ideas] of Object.entries(unscheduledActivitiesByRegion())) {
    if (ideas.length < CLUSTER_MIN) continue;
    if (state.ideasRegion && state.ideasRegion !== regionId) continue;
    const label = regionName(state.data.regions, regionId);
    banners.push(
      h(
        "div",
        { className: "banner" },
        h("div", { className: "banner-title", text: `💡 ${label.toUpperCase()} DAY?` }),
        h("div", {
          className: "muted",
          text: `${ideas.slice(0, 3).map((idea) => idea.title).join(", ")}${ideas.length > 3 ? ` +${ideas.length - 3} more` : ""} cluster nicely.`,
          style: { margin: "4px 0 10px", fontSize: "14.5px" },
        }),
        h("button", {
          className: "btn primary",
          text: "Plan this day ▸",
          type: "button",
          onclick: () =>
            dayPickerSheet({
              title: `Plan a ${label} day on…`,
              onPick: async (day) => {
                applyDay(
                  await api(`/api/days/${day.id}/items/bulk`, {
                    method: "POST",
                    memberId: state.member?.id,
                    body: { idea_ids: ideas.map((idea) => idea.id) },
                  })
                );
                toast(`${ideas.length} stops added — check the order 🚗`);
              },
            }),
        })
      )
    );
  }
  return banners;
}

function ideaCard(idea) {
  const scheduled = (idea.scheduled_day_ids || []).length > 0;
  return h(
    "div",
    {
      className: `card ${scheduled ? "dimmed" : ""}`,
      style: { borderLeftColor: REGION_COLORS[idea.region_id] || "#E4DCCE" },
    },
    h(
      "div",
      { style: { display: "flex", alignItems: "baseline", gap: "8px" } },
      h("button", {
        className: "card-title",
        text: idea.title,
        type: "button",
        style: { textAlign: "left", minHeight: "0", flex: "1" },
        onclick: () => ideaDetailSheet(idea.id),
      }),
      newPill(idea)
    ),
    h(
      "div",
      { className: "card-meta" },
      `~${fmtDur(idea.duration_min)}`,
      idea.best_time ? `Best: ${idea.best_time}` : null,
      idea.reservation_rule ? h("span", { className: "badge reservation", text: "🎟 Reservation" }) : null,
      idea.difficulty ? h("span", { className: "badge hard", text: "Hard hike" }) : null,
      scheduledBadge(idea)
    ),
    idea.notes ? h("div", { className: "card-note", text: idea.notes }) : null,
    creditLine(idea),
    h(
      "div",
      { className: "card-actions" },
      h("button", {
        className: "btn primary",
        text: "Add to a day ▾",
        type: "button",
        onclick: () => addIdeaToDay(idea),
      }),
      reactionPill(idea)
    )
  );
}

export function renderIdeas(root) {
  root.classList.add("ideas-grid");
  root.append(
    filterRow(state.ideasRegion, (regionId) => {
      state.ideasRegion = regionId;
      render();
    })
  );
  root.append(...clusterBanners());

  const activities = state.data.ideas
    .filter((idea) => idea.kind === "activity")
    .filter((idea) => !state.ideasRegion || idea.region_id === state.ideasRegion)
    .sort((a, b) => b.score - a.score || a.title.localeCompare(b.title));

  const regions = state.data.regions.filter((region) =>
    activities.some((idea) => idea.region_id === region.id)
  );

  if (!activities.length) {
    root.append(
      h("div", { className: "empty" }, h("p", { text: "No ideas here yet — add the first one!" }))
    );
  }

  for (const region of regions) {
    const group = activities.filter((idea) => idea.region_id === region.id);
    root.append(
      h(
        "div",
        { className: "region-head" },
        h("span", { className: "bar", style: { background: REGION_COLORS[region.id] } }),
        region.name,
        h("span", { className: "count", text: String(group.length) })
      ),
      h("div", { className: "region-cards" }, group.map(ideaCard))
    );
  }

  root.append(
    h(
      "div",
      { className: "fab-wrap" },
      h("button", {
        className: "btn primary",
        text: "+ Add idea",
        type: "button",
        onclick: () => addIdeaSheet("activity"),
      })
    ),
    h("button", {
      className: "btn primary block inline-add",
      text: "+ Add idea",
      type: "button",
      style: { marginTop: "16px" },
      onclick: () => addIdeaSheet("activity"),
    })
  );
}
