# WoW Character-Select Concept — nickchua.me

Mockup only, not wired into the live site. Open `index.html` in a browser
(desktop and phone) to click through it.

## Concept

The homepage becomes a warband-style character-select screen (v2 — modeled
on the modern camp-scene layout, not the classic pedestal one):

- **The scene** — an illustrated night camp (SVG, original art): four
  figures standing around a campfire with floating nameplates, each one a
  career chapter: knight = Brex RevOps (current main), robed chronicler =
  Nick's Records, artificer with hammer = side projects, athlete with
  tennis racket = UChicago. Click a figure or its list entry to select;
  the selected figure gets a gold ground-glow and gold nameplate.
- **Character list panel (right)** — warband-style: search field,
  Favorites header, entries with level + class (class-colored) + realm,
  crest icons, a ghosted "[Earlier Chapter]" slot, and a red Create
  Character button (contact CTA).
- **Description card (bottom-left)** — tooltip-style chapter highlight
  above the red Back button (Back → classic site).
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

- The camp scene becomes a 16:10 hero band up top; figures stay tappable.
- The character list panel moves below the scene as a vertical list.
- Enter World (with selected name above it) is a sticky bottom bar with
  safe-area padding; Back collapses to a small text link.
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
