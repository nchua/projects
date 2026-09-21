# WoW Character-Select Concept — nickchua.me

Mockup only, not wired into the live site. Open `index.html` in a browser
(desktop and phone) to click through it.

## Concept

The homepage becomes a character-select screen:

- **Career roster (right rail)** — each career chapter is a "character":
  Brex RevOps (current main), Nick's Records (writing), side projects,
  UChicago. Selecting one updates the center stage: name plate, realm line,
  and a chapter description panel.
- **Enter World** — plays a short loading-screen transition, then lands on
  the chapter detail: quest log (current/completed work), character sheet
  (skills as gear with rarity colors), reputation bars (cross-functional
  standing), achievements.
- **Create New Character** — the empty roster slot is the contact CTA
  (mailto).
- **View Classic Site / Writing / Newsletter** — escape hatches to the
  existing record-shop site so the blog stays reachable.

## Mobile strategy

The real game's screen is PC-only, so mobile is re-composed rather than
shrunk (breakpoint at 900px):

- Stage (name plate + emblem + description) stacks on top.
- Roster becomes a horizontal snap-scroll card rail, gacha-game style.
- Enter World is a fixed bottom bar with safe-area padding.
- Detail view collapses to a single scrolling column.

## Placeholder content (fix before anything ships)

- Levels, quest objectives, achievements in `[brackets]`, and the joke
  "equipped gear" are invented — swap in real roles, dates, and wins.
- Pre-Brex work history isn't in this repo, so the roster only has four
  chapters; add earlier roles as more characters.
- `VIEW CLASSIC SITE` / `WRITING` / `NEWSLETTER` point at
  `../../site/index.html` for now.

There is also a matching design-canvas version of these four screens as a
Claude artifact (see the session that created this folder).
