// Bits shared between the Ideas and Food boards.
import { clearVote, setVote } from "../sheets.js";
import { isNew, state } from "../state.js";
import { h } from "../ui.js";

export function reactionPill(idea) {
  const mine = state.member
    ? idea.votes.find((vote) => vote.member_id === state.member.id)
    : null;
  const thumbs = idea.votes.filter((vote) => vote.value === "interested").length;
  const stars = idea.votes.filter((vote) => vote.value === "must_go").length;

  const button = (value, icon, count) =>
    h("button", {
      type: "button",
      className: mine?.value === value ? `mine-${value}` : "",
      text: `${icon} ${count || ""}`.trim(),
      onclick: () => (mine?.value === value ? clearVote(idea.id) : setVote(idea.id, value)),
    });

  return h(
    "div",
    { className: "pill" },
    button("interested", "👍", thumbs),
    button("must_go", "⭐", stars)
  );
}

export function newPill(idea) {
  return isNew(idea) ? h("span", { className: "badge new", text: "NEW" }) : null;
}

export function scheduledBadge(idea) {
  const dayIds = idea.scheduled_day_ids || [];
  if (!dayIds.length) return null;
  const index = state.data.days.findIndex((day) => day.id === dayIds[0]);
  const day = state.data.days[index];
  let label = "✓ scheduled";
  if (day) {
    const date = day.date ? new Date(day.date + "T12:00:00") : null;
    label = `✓ ${date ? date.toLocaleDateString("en-US", { weekday: "short" }) : `Day ${index + 1}`}`;
  }
  return h("span", { className: "badge scheduled", text: label });
}

export function creditLine(idea) {
  const parts = [];
  const author = state.data.members.find((m) => m.id === idea.created_by_member_id);
  if (author) parts.push(`Added by ${author.name}`);
  if (idea.recommended_by) parts.push(`via ${idea.recommended_by}`);
  return parts.length ? h("div", { className: "voters", text: parts.join(" · ") }) : null;
}

export function voterNames(idea) {
  const members = state.data.members;
  const name = (id) => members.find((m) => m.id === id)?.name || "Someone";
  const stars = idea.votes.filter((v) => v.value === "must_go").map((v) => name(v.member_id));
  const thumbs = idea.votes.filter((v) => v.value === "interested").map((v) => name(v.member_id));
  if (!stars.length && !thumbs.length) return null;
  const row = h("div", { className: "voters" });
  if (stars.length) {
    row.append(h("span", { className: "star-names", text: `⭐ ${stars.join(", ")}` }));
  }
  if (thumbs.length) {
    if (stars.length) row.append("  ·  ");
    row.append(`👍 ${thumbs.join(", ")}`);
  }
  return row;
}
