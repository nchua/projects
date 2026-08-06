# Training Calendar PWA

Mobile-first installable web app showing the weekly lift + run training
calendar across three 2-month phases. Plain HTML/CSS/JS — no build step.

**Live URL (once Pages is enabled, see below):** https://nchua.github.io/projects/

## One-time setup: enable GitHub Pages

Everything is already deployed to the `gh-pages` branch by CI; GitHub just
needs the site switched on (the Pages "create site" API requires admin
rights no automation token can hold, so this is a manual click):

1. Repo **Settings → Pages**
2. Under *Build and deployment*: Source **Deploy from a branch**,
   Branch **gh-pages** / **(root)** → Save
3. ~1 minute later the app is live at https://nchua.github.io/projects/

After that, every push that touches `training-calendar/` republishes
automatically via `.github/workflows/deploy-training-calendar.yml`
(works from both `main` and the feature branch).

## Install on iPhone

1. Open https://nchua.github.io/projects/ in **Safari** (not Chrome).
2. Share button → **Add to Home Screen**.
3. Launches standalone (no browser chrome), works offline after first load.

## Editing the plan

All schedule data lives in [`data.js`](data.js) — phases, days, exercise
items, notes, and the 0–100 `load` value that drives each day's load-bar
width. Edit and push; nothing else needs to change. After changing any
cached file, bump `VERSION` in [`sw.js`](sw.js) so installed clients pick
up the update on next launch.

## Features

- Three phase tabs (Months 1–2 / 3–4 / 5–6), 7-day week each
- Per-day load bar — fill width reflects relative training load
- Tap a day to check it off — stored in `localStorage` keyed by ISO week,
  so it resets automatically every Monday
- Week-streak counter (consecutive fully-completed weeks)
- Offline-capable service worker; fonts self-hosted (Oswald / Inter /
  IBM Plex Mono)
- PWA setup (manifest, apple-touch-icon, standalone meta tags) mirrors the
  Caltrain app's known-good iOS install config

## Fitness-app sync

Tap **CONNECT FITNESS APP** and log in with your FitnessApp account. The
PWA then pulls `GET /calendar/weekly` from the Railway backend and:

- overlays logged actuals on each day card (`LOGGED 2.6 MI · 30 MIN ·
  152 BPM` for runs, `SQ 245×3 · BP 205×5` top sets for lifts)
- auto-checks days that have a synced session of the matching type
- shows a pace strip (`WK 5 · 4.8/9.6 MI · 2 LIFTS · ON PACE`) that
  expands into the report: weekly mileage expected-vs-actual, long-run
  progression, and best-e1RM deltas for squat/deadlift/bench/OHP

"Expected" mileage ramps linearly through each phase's `milesMin →
milesMax` (set in `data.js`), with every 4th plan week cut ~25%. The plan
start date (Monday of week 1) is set in the connect dialog and stored
locally. The verdict pro-rates mid-week, and flags **AHEAD — EASE UP**
when ramping too fast (that's how the 2024 injury happened).

Runs arrive via the iOS app's Apple Health import (now including
distance); lifts are whatever you log in the app. Actuals cache in
`localStorage` so the last sync renders offline. Tokens also live in
`localStorage` — fine for a personal device; use DISCONNECT to clear.

**Goes live when the branch merges to `main`** (Railway auto-deploys the
backend; `alembic upgrade head` runs the distance migration). Until then
the connect button will log in but find no `/calendar/weekly` endpoint on
prod. For local testing:
`localStorage.setItem("tc.apiBase", "http://localhost:8000")`.
