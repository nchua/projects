// Food board: ranked restaurant cards with Yelp link-outs and voting.
import { addIdeaSheet, addIdeaToDay, ideaDetailSheet } from "../sheets.js";
import { render, state } from "../state.js";
import { REGION_COLORS, h, regionChip, yelpUrl } from "../ui.js";
import { creditLine, newPill, reactionPill, scheduledBadge, voterNames } from "./shared.js";

function controls() {
  const row = h("div", { className: "filter-row" });
  const sortChip = (id, label) =>
    h("button", {
      type: "button",
      className: `chip ${state.eatsSort === id ? "active" : ""}`,
      text: label,
      onclick: () => {
        state.eatsSort = id;
        render();
      },
    });
  row.append(sortChip("ranked", "Ranked"), sortChip("newest", "Newest"));

  const regionChipBtn = (id, label) =>
    h("button", {
      type: "button",
      className: `chip ${state.eatsRegion === id ? "active" : ""}`,
      text: label,
      onclick: () => {
        state.eatsRegion = id;
        render();
      },
    });
  row.append(regionChipBtn(null, "All regions"));
  for (const region of state.data.regions) {
    if (state.data.ideas.some((idea) => idea.kind === "restaurant" && idea.region_id === region.id)) {
      row.append(regionChipBtn(region.id, region.name));
    }
  }
  return row;
}

function eatCard(idea, rank) {
  const stars = idea.votes.filter((vote) => vote.value === "must_go").length;
  return h(
    "div",
    {
      className: "card eat-card",
      style: { borderLeftColor: REGION_COLORS[idea.region_id] || "#E4DCCE" },
    },
    state.eatsSort === "ranked" ? h("div", { className: "rank", text: String(rank) }) : null,
    h(
      "div",
      { className: "body" },
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
        regionChip(state.data.regions, idea.region_id),
        idea.meal_tags?.length ? idea.meal_tags.join(" · ") : null,
        scheduledBadge(idea)
      ),
      voterNames(idea),
      idea.notes ? h("div", { className: "card-note", text: idea.notes }) : null,
      creditLine(idea),
      h(
        "div",
        { className: "card-actions" },
        h("a", {
          className: "btn yelp",
          text: idea.yelp_url ? "Yelp ↗" : "Search Yelp ↗",
          href: yelpUrl(idea),
          target: "_blank",
          rel: "noopener",
        }),
        h("button", {
          className: "btn",
          text: "Add to a day ▾",
          type: "button",
          onclick: () => addIdeaToDay(idea),
        }),
        reactionPill(idea)
      )
    )
  );
}

export function renderEats(root) {
  root.append(controls());

  let restaurants = state.data.ideas
    .filter((idea) => idea.kind === "restaurant")
    .filter((idea) => !state.eatsRegion || idea.region_id === state.eatsRegion);

  if (state.eatsSort === "newest") {
    restaurants.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  } else {
    restaurants.sort((a, b) => {
      const aStars = a.votes.filter((vote) => vote.value === "must_go").length;
      const bStars = b.votes.filter((vote) => vote.value === "must_go").length;
      return b.score - a.score || bStars - aStars || (a.created_at || "").localeCompare(b.created_at || "");
    });
  }

  if (!restaurants.length) {
    root.append(
      h("div", { className: "empty" }, h("p", { text: "No suggestions yet — start the list!" }))
    );
  }

  restaurants.forEach((idea, index) => root.append(eatCard(idea, index + 1)));

  root.append(
    h(
      "div",
      { className: "fab-wrap" },
      h("button", {
        className: "btn primary",
        text: "+ Suggest a restaurant",
        type: "button",
        onclick: () => addIdeaSheet("restaurant"),
      })
    ),
    h("button", {
      className: "btn primary block inline-add",
      text: "+ Suggest a restaurant",
      type: "button",
      style: { marginTop: "16px" },
      onclick: () => addIdeaSheet("restaurant"),
    })
  );
}
