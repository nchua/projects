// Itinerary view: day strip / week rail, spine timeline, desktop cockpit.
import { api } from "../api.js";
import { addStopSheet, dayEditSheet, stopMenuSheet, templatesSheet } from "../sheets.js";
import { applyDay, render, state } from "../state.js";
import {
  HOME_NAME,
  REGION_COLORS,
  dayShort,
  dayTitle,
  fmtDur,
  fmtTime,
  h,
  mapsDirUrl,
  regionChip,
} from "../ui.js";

function dominantRegion(day) {
  const counts = {};
  for (const item of day.items) {
    counts[item.region_id] = (counts[item.region_id] || 0) + 1;
  }
  return Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0] || null;
}

function dayChip(day, index, { rail = false } = {}) {
  const short = dayShort(day, index);
  const region = dominantRegion(day);
  return h(
    "button",
    {
      type: "button",
      className: `daychip ${day.id === state.dayId ? "active" : ""}`,
      onclick: () => {
        state.dayId = day.id;
        state.reorderMode = false;
        location.hash = `#/day/${day.id}`;
        render();
      },
    },
    h("span", { className: "dow", text: `${short.dow}${short.sub ? " " + short.sub : ""}` }),
    rail && day.label ? h("span", { text: day.label, style: { fontSize: "12px" } }) : null,
    rail
      ? h("span", { text: day.items.length ? `${day.items.length} stops` : "empty", style: { fontSize: "12px" } })
      : null,
    region
      ? h("span", { className: "region-dot", style: { background: REGION_COLORS[region] } })
      : null
  );
}

function driveRow(minutes, flags, originTitle, destTitle, destMapsUrl) {
  const rush = (flags || []).length > 0;
  return h(
    "div",
    { className: `drive-row ${rush ? "rush" : ""}` },
    `🚗 ~${minutes} min drive${rush ? " ⚠ rush-hour risk" : ""}`,
    h("a", {
      text: "Directions ↗",
      href: mapsDirUrl(originTitle, destTitle, destMapsUrl),
      target: "_blank",
      rel: "noopener",
      style: { marginLeft: "auto" },
    })
  );
}

function stopCard(day, item) {
  const timeText = `${fmtTime(item.start)} – ${fmtTime(item.end)}`;
  return h(
    "div",
    { className: "stop-row" },
    h(
      "div",
      { className: "card", style: { borderLeftColor: REGION_COLORS[item.region_id] || "#E4DCCE" } },
      h(
        "div",
        { className: "stop-time" },
        item.fixed_start_time ? h("span", { className: "pin", text: "📌" }) : null,
        timeText
      ),
      h("div", { className: "card-title", text: item.title }),
      h(
        "div",
        { className: "card-meta" },
        regionChip(state.data.regions, item.region_id),
        fmtDur(item.duration_min),
        item.leave_by && day.items[0]?.id === item.id
          ? h("span", { className: "badge scheduled", text: `Leave hotel by ${fmtTime(item.leave_by)}` })
          : null,
        item.reservation_rule ? h("span", { className: "badge reservation", text: "🎟 Reservation" }) : null,
        item.difficulty ? h("span", { className: "badge hard", text: `${item.difficulty} hike` }) : null
      ),
      item.notes ? h("div", { className: "card-note", text: item.notes }) : null,
      ...item.warnings.map((warning) => h("div", { className: "warn-row", text: `⚠ ${warning.message}` })),
      h(
        "div",
        { className: "card-actions" },
        item.yelp_url ? h("a", { className: "btn yelp", text: "Yelp ↗", href: item.yelp_url, target: "_blank", rel: "noopener" }) : null,
        h("button", {
          className: "btn",
          text: "•••",
          type: "button",
          "aria-label": "Stop options",
          onclick: () => stopMenuSheet(day, item),
        })
      )
    )
  );
}

function spine(day) {
  const container = h("div", { className: "spine" });
  container.append(
    h(
      "div",
      { className: "stop-row home" },
      h(
        "div",
        { className: "card" },
        h("div", { className: "stop-time", text: fmtTime(day.start_time) }),
        h("div", { className: "card-title", text: HOME_NAME }),
        h("div", { className: "card-meta" }, "Home base — day starts here")
      )
    )
  );

  let prevTitle = HOME_NAME;
  for (const item of day.items) {
    if (item.free_gap_min) {
      container.append(h("div", { className: "free-row", text: `🌤 Free time — ${fmtDur(item.free_gap_min)}` }));
    }
    container.append(driveRow(item.drive_minutes, item.drive_flags, prevTitle, item.title, item.maps_url));
    container.append(stopCard(day, item));
    prevTitle = item.title;
  }

  if (day.return_leg) {
    container.append(
      driveRow(day.return_leg.drive_minutes, day.return_leg.drive_flags, prevTitle, HOME_NAME, null)
    );
    container.append(
      h(
        "div",
        { className: "stop-row home" },
        h(
          "div",
          { className: "card" },
          h("div", { className: "stop-time", text: `~${fmtTime(day.return_leg.arrive_hotel)}` }),
          h("div", { className: "card-title", text: "Back at the hotel" })
        )
      )
    );
  }
  return container;
}

function reorderList(day) {
  const container = h("div", {});
  const order = day.items.map((item) => item.id);

  const commit = async () => {
    applyDay(
      await api(`/api/days/${day.id}/order`, {
        method: "PUT",
        memberId: state.member?.id,
        body: { item_ids: order },
      })
    );
  };

  day.items.forEach((item, index) => {
    const row = h(
      "div",
      { className: "reorder-row" },
      h("span", { className: "title", text: `${index + 1}. ${item.title}` }),
      h("button", {
        type: "button",
        text: "▲",
        disabled: index === 0,
        onclick: () => {
          [order[index - 1], order[index]] = [order[index], order[index - 1]];
          commit();
        },
      }),
      h("button", {
        type: "button",
        text: "▼",
        disabled: index === day.items.length - 1,
        onclick: () => {
          [order[index + 1], order[index]] = [order[index], order[index + 1]];
          commit();
        },
      })
    );
    container.append(row);
  });
  return container;
}

function emptyState(day) {
  const clusters = clusterHint();
  return h(
    "div",
    { className: "empty" },
    h("p", { text: `Nothing planned yet${day.label ? ` for ${day.label}` : ""}.` }),
    h("button", {
      className: "btn primary block",
      text: "Browse the Idea Pool",
      type: "button",
      onclick: () => {
        state.tab = "ideas";
        location.hash = "#/ideas";
        render();
      },
    }),
    h("button", { className: "btn block", text: "+ Add a stop", type: "button", onclick: () => addStopSheet(day.id) }),
    state.data.day_templates?.length
      ? h("button", {
          className: "btn block",
          text: "Or start from a day plan ▸",
          type: "button",
          onclick: () => templatesSheet(day.id),
        })
      : null,
    clusters
  );
}

function clusterHint() {
  const unscheduled = state.data.ideas.filter(
    (idea) => idea.kind === "activity" && !(idea.scheduled_day_ids || []).length
  );
  const byRegion = {};
  for (const idea of unscheduled) {
    (byRegion[idea.region_id] ||= []).push(idea);
  }
  const best = Object.entries(byRegion).sort((a, b) => b[1].length - a[1].length)[0];
  if (!best || best[1].length < 3) return null;
  const region = state.data.regions.find((r) => r.id === best[0]);
  return h("p", {
    className: "muted",
    text: `💡 ${best[1].length} ${region?.name || best[0]} ideas in the pool would make a great day together`,
    style: { marginTop: "12px" },
  });
}

function contextPanel(day) {
  const panel = h("div", { className: "context-panel" });
  const dominant = dominantRegion(day);
  const unscheduled = state.data.ideas
    .filter((idea) => !(idea.scheduled_day_ids || []).length)
    .sort((a, b) => {
      const aDom = a.region_id === dominant ? 0 : 1;
      const bDom = b.region_id === dominant ? 0 : 1;
      return aDom - bDom || b.score - a.score;
    });

  const section = (title, ideas) => {
    if (!ideas.length) return;
    panel.append(h("h3", { text: title }));
    for (const idea of ideas.slice(0, 6)) {
      panel.append(
        h(
          "div",
          { className: "card", style: { borderLeftColor: REGION_COLORS[idea.region_id] } },
          h("div", { className: "card-title", text: idea.title }),
          h("div", { className: "card-meta" }, fmtDur(idea.duration_min), idea.score ? `${idea.score} pts` : ""),
          h(
            "div",
            { className: "card-actions" },
            h("button", {
              className: "btn",
              text: "+ Add",
              type: "button",
              onclick: async () => {
                applyDay(
                  await api(`/api/days/${day.id}/items`, {
                    method: "POST",
                    memberId: state.member?.id,
                    body: { idea_id: idea.id },
                  })
                );
              },
            })
          )
        )
      );
    }
  };

  section("Add to this day", unscheduled.filter((idea) => idea.kind === "activity"));
  section("Top eats not yet planned", unscheduled.filter((idea) => idea.kind === "restaurant").sort((a, b) => b.score - a.score));
  return panel;
}

export function renderSchedule(root) {
  const days = state.data.days;
  const day = days.find((entry) => entry.id === state.dayId) || days[0];
  if (!day) {
    root.append(h("div", { className: "empty" }, h("p", { text: "No days yet." })));
    return;
  }

  root.classList.add("cockpit");
  const index = days.indexOf(day);

  root.append(
    h("div", { className: "week-rail" }, days.map((entry, i) => dayChip(entry, i, { rail: true })))
  );

  const main = h("div", {});
  main.append(h("div", { className: "daystrip" }, days.map((entry, i) => dayChip(entry, i))));

  const overpacked = day.warnings.find((warning) => warning.code === "overpacked");
  main.append(
    h(
      "div",
      { className: "dayhead" },
      h("h2", { text: dayTitle(day, index) }),
      h(
        "div",
        { className: "sub" },
        h("button", {
          className: "btn subtle",
          type: "button",
          text: `Leaves hotel ${fmtTime(day.start_time)} ✎`,
          style: { minHeight: "34px", padding: "0" },
          onclick: () => dayEditSheet(day),
        }),
        day.items.length ? `🚗 ${fmtDur(day.total_drive_minutes)} total` : null,
        overpacked ? h("span", { className: "badge warn", text: overpacked.message }) : null,
        day.notes ? h("span", { text: day.notes }) : null
      )
    )
  );

  if (!day.items.length) {
    main.append(emptyState(day));
  } else if (state.reorderMode) {
    main.append(
      h("button", {
        className: "btn primary block",
        text: "Done reordering",
        type: "button",
        style: { marginBottom: "10px" },
        onclick: () => {
          state.reorderMode = false;
          render();
        },
      }),
      reorderList(day)
    );
  } else {
    main.append(
      h(
        "div",
        { style: { display: "flex", gap: "8px", marginBottom: "4px" } },
        h("button", {
          className: "btn",
          text: "Reorder",
          type: "button",
          onclick: () => {
            state.reorderMode = true;
            render();
          },
        }),
        h("button", { className: "btn primary", text: "+ Add a stop", type: "button", onclick: () => addStopSheet(day.id) })
      ),
      spine(day)
    );
  }
  root.append(main);
  root.append(contextPanel(day));
}
