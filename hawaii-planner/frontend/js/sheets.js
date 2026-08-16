// All bottom sheets: add/edit forms, pickers, menus, the star-swap flow.
import { api, ApiError } from "./api.js";
import { applyDay, applyIdea, refresh, state } from "./state.js";
import {
  closeSheet,
  field,
  fmtClosedDays,
  fmtDur,
  dayShort,
  dayTitle,
  h,
  openSheet,
  regionChip,
  regionChipRow,
  stepper,
  toast,
} from "./ui.js";

const memberId = () => state.member?.id;

// ── Voting (with the star-budget swap flow) ────────────────
export async function setVote(ideaId, value) {
  try {
    const payload = await api(`/api/ideas/${ideaId}/vote`, {
      method: "PUT",
      body: { value },
      memberId: memberId(),
    });
    applyIdea(payload);
  } catch (error) {
    if (error instanceof ApiError && error.code === "must_go_budget_exceeded") {
      starSwapSheet(ideaId, error.detail.current_must_go_idea_ids || []);
    }
  }
}

export async function clearVote(ideaId) {
  applyIdea(
    await api(`/api/ideas/${ideaId}/vote`, { method: "DELETE", memberId: memberId() })
  );
}

function starSwapSheet(targetId, currentIds) {
  const ideas = currentIds
    .map((id) => state.data.ideas.find((idea) => idea.id === id))
    .filter(Boolean);
  const sheet = openSheet(
    "Move your must-go?",
    h("p", {
      className: "muted",
      text: "You've used all 3 must-go stars on this board. Pick one to move:",
      style: { marginBottom: "12px" },
    })
  );
  for (const idea of ideas) {
    sheet.append(
      h(
        "button",
        {
          className: "row-btn",
          type: "button",
          onclick: async () => {
            closeSheet();
            // Demote the old star to 👍 (they cared enough to star it once).
            await api(`/api/ideas/${idea.id}/vote`, {
              method: "PUT",
              body: { value: "interested" },
              memberId: memberId(),
            }).then(applyIdea);
            await setVote(targetId, "must_go");
            toast("Must-go moved ⭐");
          },
        },
        `⭐ ${idea.title}`,
        h("span", { className: "sub", text: "Move this star" })
      )
    );
  }
}

// ── Idea add / detail / edit ───────────────────────────────
export function addIdeaSheet(kind) {
  const isFood = kind === "restaurant";
  let regionId = isFood ? "WAI" : null;
  let duration = isFood ? 75 : 90;

  const title = h("input", { placeholder: isFood ? "Restaurant name" : "What's the idea?", maxLength: 120 });
  const yelp = h("input", { placeholder: "https://www.yelp.com/biz/…", inputMode: "url" });
  const notes = h("input", { placeholder: isFood ? "Dish tips, cash-only, etc." : "Anything the family should know" });

  const sheet = openSheet(
    isFood ? "Suggest a restaurant" : "Add an idea",
    field("Name", title),
    field("Region", regionChipRow(state.data.regions, regionId, (id) => (regionId = id))),
    isFood
      ? field(
          "Yelp link (optional)",
          h(
            "div",
            {},
            yelp,
            h("a", {
              text: "Find it on Yelp ↗",
              href: "https://www.yelp.com/search?find_loc=Honolulu%2C+HI",
              target: "_blank",
              rel: "noopener",
              style: { fontSize: "14px", display: "inline-block", marginTop: "6px" },
            })
          )
        )
      : null,
    field("Rough duration", stepper({ value: duration, onChange: (v) => (duration = v) })),
    field("Notes (optional)", notes),
    h("button", {
      className: "btn primary block",
      text: isFood ? "Add to the food board" : "Add to the pool",
      type: "button",
      onclick: async () => {
        if (!title.value.trim()) return toast("Give it a name first", "error");
        if (!regionId) return toast("Pick a region", "error");
        const payload = await api("/api/ideas", {
          method: "POST",
          memberId: memberId(),
          body: {
            title: title.value.trim(),
            kind,
            region_id: regionId,
            duration_min: duration,
            yelp_url: isFood && yelp.value.trim() ? yelp.value.trim() : null,
            notes: notes.value.trim() || null,
          },
        });
        applyIdea(payload);
        closeSheet();
        toast(isFood ? "Added — time to vote 🤙" : "Added to the pool 🌺");
      },
    })
  );
  title.focus();
  return sheet;
}

export function ideaDetailSheet(ideaId) {
  const idea = state.data.ideas.find((entry) => entry.id === ideaId);
  if (!idea) return;
  const members = state.data.members;
  const voteRows = idea.votes.map((vote) => {
    const member = members.find((entry) => entry.id === vote.member_id);
    return h("div", {
      text: `${vote.value === "must_go" ? "⭐" : "👍"} ${member ? member.name : "Someone"}`,
      style: { padding: "3px 0" },
    });
  });

  const infoRows = [];
  const addInfo = (label, value) => {
    if (value) {
      infoRows.push(
        h("div", { style: { marginBottom: "8px" } }, h("strong", { text: `${label}: ` }), value)
      );
    }
  };
  addInfo("Duration", fmtDur(idea.duration_min));
  addInfo("Best time", idea.best_time);
  addInfo("Reservations", idea.reservation_rule);
  addInfo("Closed", fmtClosedDays(idea.closed_days));
  addInfo("Difficulty", idea.difficulty);
  addInfo("Recommended by", idea.recommended_by);
  addInfo("Notes", idea.notes);
  const addedBy = members.find((entry) => entry.id === idea.created_by_member_id);
  if (addedBy) addInfo("Added by", addedBy.name);

  openSheet(
    idea.title,
    h("div", { style: { marginBottom: "10px" } }, regionChip(state.data.regions, idea.region_id)),
    ...infoRows,
    voteRows.length
      ? h("div", { style: { margin: "10px 0" } }, h("strong", { text: "Votes" }), ...voteRows)
      : null,
    h(
      "div",
      { className: "card-actions" },
      idea.kind === "restaurant"
        ? h("a", { className: "btn yelp", text: "Yelp ↗", href: idea.yelp_url || `https://www.yelp.com/search?${new URLSearchParams({ find_desc: idea.title, find_loc: "Honolulu, HI" })}`, target: "_blank", rel: "noopener" })
        : null,
      h("a", {
        className: "btn",
        text: "Maps ↗",
        href: idea.maps_url || `https://www.google.com/maps/search/?${new URLSearchParams({ api: "1", query: `${idea.title}, Oahu, HI` })}`,
        target: "_blank",
        rel: "noopener",
      }),
      h("button", { className: "btn", text: "Edit", type: "button", onclick: () => editIdeaSheet(idea.id) }),
      h("button", {
        className: "btn danger",
        text: "Delete",
        type: "button",
        onclick: () => confirmDeleteIdea(idea),
      })
    )
  );
}

function confirmDeleteIdea(idea) {
  const scheduled = (idea.scheduled_day_ids || []).length > 0;
  openSheet(
    `Delete ${idea.title}?`,
    h("p", {
      className: "muted",
      text: scheduled
        ? "It's on the schedule — deleting removes it from those days too."
        : "This removes it for everyone.",
      style: { marginBottom: "14px" },
    }),
    h("button", {
      className: "btn danger block",
      text: "Delete for everyone",
      type: "button",
      onclick: async () => {
        await api(`/api/ideas/${idea.id}`, { method: "DELETE", memberId: memberId() });
        closeSheet();
        await refresh(); // cascade touched days too
        toast("Deleted");
      },
    })
  );
}

export function editIdeaSheet(ideaId) {
  const idea = state.data.ideas.find((entry) => entry.id === ideaId);
  if (!idea) return;
  let regionId = idea.region_id;
  let duration = idea.duration_min;
  const title = h("input", { value: idea.title, maxLength: 120 });
  const yelp = h("input", { value: idea.yelp_url || "", inputMode: "url" });
  const notes = h("input", { value: idea.notes || "" });

  openSheet(
    "Edit idea",
    field("Name", title),
    field("Region", regionChipRow(state.data.regions, regionId, (id) => (regionId = id))),
    idea.kind === "restaurant" ? field("Yelp link", yelp) : null,
    field("Duration", stepper({ value: duration, onChange: (v) => (duration = v) })),
    field("Notes", notes),
    h("button", {
      className: "btn primary block",
      text: "Save",
      type: "button",
      onclick: async () => {
        const payload = await api(`/api/ideas/${idea.id}`, {
          method: "PATCH",
          memberId: memberId(),
          body: {
            title: title.value.trim(),
            region_id: regionId,
            duration_min: duration,
            yelp_url: idea.kind === "restaurant" ? yelp.value.trim() || null : undefined,
            notes: notes.value.trim() || null,
          },
        });
        applyIdea(payload);
        closeSheet();
        await refresh(); // region/duration changes ripple into day timelines
      },
    })
  );
}

// ── Day picker (shared by add-to-day, cluster plan, move stop) ─
export function dayPickerSheet({ title, closedDays = [], onPick }) {
  const sheet = openSheet(title);
  state.data.days.forEach((day, index) => {
    const short = dayShort(day, index);
    const weekday = day.date
      ? ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][new Date(day.date + "T12:00:00").getDay() === 0 ? 6 : new Date(day.date + "T12:00:00").getDay() - 1]
      : null;
    const isClosed = weekday && closedDays.includes(weekday);
    const stops = day.items.length;
    sheet.append(
      h(
        "button",
        {
          className: `row-btn ${isClosed ? "disabled" : ""}`,
          type: "button",
          onclick: () => {
            if (isClosed) return toast(`Closed that day (${fmtClosedDays(closedDays)})`, "error");
            closeSheet();
            onPick(day);
          },
        },
        h(
          "span",
          { style: { flex: "1" } },
          dayTitle(day, index),
          h("span", {
            className: "sub",
            text: isClosed
              ? `✕ Closed ${short.dow}`
              : `${stops ? `${stops} stop${stops > 1 ? "s" : ""}` : "Nothing planned yet"}${day.label ? "" : ""}`,
          })
        )
      )
    );
  });
  return sheet;
}

export function addIdeaToDay(idea) {
  dayPickerSheet({
    title: `Add “${idea.title}” to…`,
    closedDays: idea.closed_days || [],
    onPick: async (day) => {
      if (idea.reservation_rule) toast(`🎟 ${idea.reservation_rule}`.slice(0, 120));
      const payload = await api(`/api/days/${day.id}/items`, {
        method: "POST",
        memberId: memberId(),
        body: { idea_id: idea.id },
      });
      applyDay(payload);
      toast(
        idea.kind === "restaurant"
          ? "Added — tap the stop to pin a meal time"
          : "Added to the day 🌴"
      );
    },
  });
}

// ── Add stop to a specific day ─────────────────────────────
export function addStopSheet(dayId) {
  const sheet = openSheet(
    "Add a stop",
    h("button", {
      className: "row-btn",
      type: "button",
      text: "🌴 From the Idea Pool",
      onclick: () => poolPickerSheet(dayId, "activity"),
    }),
    h("button", {
      className: "row-btn",
      type: "button",
      text: "🍽 From the Food Board",
      onclick: () => poolPickerSheet(dayId, "restaurant"),
    }),
    h("p", { className: "muted", text: "— or type a new one —", style: { textAlign: "center", margin: "10px 0" } })
  );

  let regionId = null;
  let duration = 90;
  const title = h("input", { placeholder: "e.g. Rest at the hotel", maxLength: 120 });
  const pin = h("input", { type: "time" });
  sheet.append(
    field("Name", title),
    field("Region (optional — stays put if blank)", regionChipRow(state.data.regions, null, (id) => (regionId = id))),
    field("Duration", stepper({ value: duration, onChange: (v) => (duration = v) })),
    field("Pin a start time (optional)", pin),
    h("button", {
      className: "btn primary block",
      text: "Add stop",
      type: "button",
      onclick: async () => {
        if (!title.value.trim()) return toast("Give the stop a name", "error");
        const payload = await api(`/api/days/${dayId}/items`, {
          method: "POST",
          memberId: memberId(),
          body: {
            free_text_title: title.value.trim(),
            free_text_region_id: regionId,
            duration_override_min: duration,
            fixed_start_time: pin.value || null,
          },
        });
        applyDay(payload);
        closeSheet();
      },
    })
  );
}

function poolPickerSheet(dayId, kind) {
  const ideas = state.data.ideas
    .filter((idea) => idea.kind === kind)
    .sort((a, b) => {
      const aScheduled = (a.scheduled_day_ids || []).length > 0;
      const bScheduled = (b.scheduled_day_ids || []).length > 0;
      if (aScheduled !== bScheduled) return aScheduled ? 1 : -1;
      return b.score - a.score || a.title.localeCompare(b.title);
    });
  const sheet = openSheet(kind === "restaurant" ? "Pick a restaurant" : "Pick an idea");
  for (const idea of ideas) {
    const scheduled = (idea.scheduled_day_ids || []).length > 0;
    sheet.append(
      h(
        "button",
        {
          className: "row-btn",
          type: "button",
          onclick: async () => {
            const payload = await api(`/api/days/${dayId}/items`, {
              method: "POST",
              memberId: memberId(),
              body: { idea_id: idea.id },
            });
            applyDay(payload);
            closeSheet();
          },
        },
        h(
          "span",
          { style: { flex: "1" } },
          idea.title,
          h("span", {
            className: "sub",
            text: `${state.data.regions.find((r) => r.id === idea.region_id)?.name || ""} · ${fmtDur(idea.duration_min)}${idea.score ? ` · ${idea.score} pts` : ""}${scheduled ? " · ✓ scheduled" : ""}`,
          })
        )
      )
    );
  }
}

// ── Stop menu / edit ───────────────────────────────────────
export function stopMenuSheet(day, item) {
  const items = day.items;
  const index = items.findIndex((entry) => entry.id === item.id);

  const move = async (delta) => {
    const order = items.map((entry) => entry.id);
    const target = index + delta;
    if (target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    closeSheet();
    applyDay(await api(`/api/days/${day.id}/order`, { method: "PUT", memberId: memberId(), body: { item_ids: order } }));
  };

  openSheet(
    item.title,
    index > 0
      ? h("button", { className: "row-btn", type: "button", text: "⬆️ Move up", onclick: () => move(-1) })
      : null,
    index < items.length - 1
      ? h("button", { className: "row-btn", type: "button", text: "⬇️ Move down", onclick: () => move(1) })
      : null,
    h("button", {
      className: "row-btn",
      type: "button",
      text: "📆 Move to another day…",
      onclick: () =>
        dayPickerSheet({
          title: "Move to…",
          onPick: async (target) => {
            await api(`/api/items/${item.id}`, {
              method: "PATCH",
              memberId: memberId(),
              body: { trip_day_id: target.id },
            });
            await refresh(); // both days changed
            toast("Moved");
          },
        }),
    }),
    h("button", { className: "row-btn", type: "button", text: "✏️ Edit stop", onclick: () => stopEditSheet(day, item) }),
    h("button", {
      className: "row-btn",
      type: "button",
      text: item.idea_id ? "🗑 Remove (stays in the pool)" : "🗑 Remove",
      onclick: async () => {
        closeSheet();
        applyDay(await api(`/api/items/${item.id}`, { method: "DELETE", memberId: memberId() }));
        toast("Removed from the day");
      },
    })
  );
}

export function stopEditSheet(day, item) {
  let duration = item.duration_min;
  let driveOverride = item.drive_override_min;
  const pin = h("input", { type: "time", value: item.fixed_start_time || "" });
  const notes = h("input", { value: item.notes || "", placeholder: "e.g. reservation under Nick" });

  const driveWrap = h("div", {});
  const renderDrive = () => {
    driveWrap.replaceChildren(
      stepper({
        value: driveOverride ?? item.drive_minutes,
        min: 0,
        max: 240,
        step: 5,
        onChange: (v) => (driveOverride = v),
      }),
      h("button", {
        className: "btn subtle",
        type: "button",
        text: "Reset to estimate",
        onclick: () => {
          driveOverride = null;
          renderDrive();
        },
      })
    );
  };
  renderDrive();

  openSheet(
    `Edit ${item.title}`,
    field("Duration", stepper({ value: duration, onChange: (v) => (duration = v) })),
    field("Pinned start time (reservations)", pin),
    field("Drive time into this stop", driveWrap),
    field("Notes", notes),
    h("button", {
      className: "btn primary block",
      text: "Save",
      type: "button",
      onclick: async () => {
        const payload = await api(`/api/items/${item.id}`, {
          method: "PATCH",
          memberId: memberId(),
          body: {
            duration_override_min: duration,
            fixed_start_time: pin.value || null,
            drive_override_min: driveOverride,
            notes: notes.value.trim() || null,
          },
        });
        applyDay(payload);
        closeSheet();
      },
    })
  );
}

// ── Day edit ───────────────────────────────────────────────
export function dayEditSheet(day) {
  const label = h("input", { value: day.label || "", placeholder: "e.g. North Shore day", maxLength: 80 });
  const start = h("input", { type: "time", value: day.start_time });
  const end = h("input", { type: "time", value: day.end_time });
  const notes = h("input", { value: day.notes || "" });

  openSheet(
    "Edit day",
    field("Label", label),
    field("Leave hotel at", start),
    field("Aim to be back by", end),
    field("Notes", notes),
    h("button", {
      className: "btn primary block",
      text: "Save",
      type: "button",
      onclick: async () => {
        const payload = await api(`/api/days/${day.id}`, {
          method: "PATCH",
          memberId: memberId(),
          body: {
            label: label.value.trim() || null,
            start_time: start.value,
            end_time: end.value,
            notes: notes.value.trim() || null,
          },
        });
        applyDay(payload);
        closeSheet();
      },
    })
  );
}

// ── Day templates ──────────────────────────────────────────
export function templatesSheet(dayId) {
  const sheet = openSheet("Start from a day plan");
  for (const template of state.data.day_templates) {
    sheet.append(
      h(
        "button",
        {
          className: "row-btn",
          type: "button",
          onclick: () => templatePreviewSheet(dayId, template),
        },
        h(
          "span",
          { style: { flex: "1" } },
          template.name,
          h("span", { className: "sub", text: `${template.description} · ${template.stops.length} stops` })
        )
      )
    );
  }
}

function templatePreviewSheet(dayId, template) {
  const byTitle = new Map(
    state.data.ideas.map((idea) => [idea.title.toLowerCase(), idea])
  );
  const sheet = openSheet(
    template.name,
    h("p", { className: "muted", text: template.pacing_note || template.description, style: { marginBottom: "12px" } })
  );
  for (const stop of template.stops) {
    sheet.append(
      h("div", { className: "row-btn", style: { cursor: "default" } },
        h("span", { style: { flex: "1" } }, stop.title,
          h("span", { className: "sub", text: `${state.data.regions.find((r) => r.id === stop.region_id)?.name || ""} · ${fmtDur(stop.duration_min)}` })
        )
      )
    );
  }
  sheet.append(
    h("button", {
      className: "btn primary block",
      text: "Use this plan",
      type: "button",
      onclick: async () => {
        closeSheet();
        // Sequential adds preserve the template's curated stop order.
        let payload = null;
        for (const stop of template.stops) {
          const idea = byTitle.get(stop.title.toLowerCase());
          payload = await api(`/api/days/${dayId}/items`, {
            method: "POST",
            memberId: memberId(),
            body: idea
              ? { idea_id: idea.id }
              : {
                  free_text_title: stop.title,
                  free_text_region_id: stop.region_id,
                  duration_override_min: stop.duration_min,
                },
          });
        }
        if (payload) applyDay(payload);
        toast(`${template.name} loaded — tweak away 🤙`);
      },
    })
  );
}

// ── You-chip ───────────────────────────────────────────────
export function youSheet(onSwitch) {
  const trip = state.data;
  openSheet(
    state.member ? `You're ${state.member.name}` : "Who are you?",
    h("p", { className: "muted", text: "Votes and suggestions are saved under your name on this phone.", style: { marginBottom: "12px" } }),
    h("button", {
      className: "btn block",
      type: "button",
      text: "Switch person",
      onclick: () => {
        closeSheet();
        onSwitch();
      },
    }),
    h("div", { style: { marginTop: "16px" } },
      h("strong", { text: "The crew" }),
      ...trip.members.map((member) => h("div", { text: member.name, style: { padding: "4px 0" } }))
    ),
    h("p", { className: "muted", text: "Aug 26 – 31, 2026 · Aston Waikiki Beach Tower", style: { marginTop: "14px" } })
  );
}
