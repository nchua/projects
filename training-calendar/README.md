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

## Future: fitness-app sync

The plan is to sync this with the FitnessApp backend (Railway): pull logged
workouts via `GET /api/workouts` to auto-check days and show actuals next
to targets. That needs auth + CORS on the backend, so it's deliberately not
wired up in this static v1; `data.js`'s shape (items as [name, spec] pairs)
is designed to accept an `actual` field alongside each target later.
