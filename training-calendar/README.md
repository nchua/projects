# Training Calendar PWA

Mobile-first installable web app showing the weekly lift + run training
calendar across three ~8-week phases. Plain HTML/CSS/JS — no build step.

**Live:** https://nchua.github.io/projects/

## Install on iPhone

1. Open the URL above in Safari.
2. Share → **Add to Home Screen**.
3. Launches standalone (no browser chrome), works offline after first load.

## Editing the plan

All schedule data lives in [`data.js`](data.js) — phases, days, spec lines,
and the 0–100 `load` value that drives each day's load-bar width. Edit and
push; no other file needs to change. After changing any cached file, bump
`VERSION` in [`sw.js`](sw.js) so installed clients pick up the update.

## Deploy

Pushed automatically to GitHub Pages by
[`.github/workflows/deploy-training-calendar.yml`](../.github/workflows/deploy-training-calendar.yml)
on pushes touching `training-calendar/`. The site is static — it can be
rehosted anywhere (Netlify/Vercel/Railway static) by serving this directory;
all asset paths are relative.

## Features

- Three phase tabs (Base / Build / Peak), 7-day week each
- Tap a day to check it off — stored in `localStorage`, keyed by ISO week,
  so it resets automatically every Monday
- Week-streak counter (consecutive fully-completed weeks)
- Offline-capable via service worker; fonts self-hosted
- Every phase carries the "every 4th week: −25% mileage" cutback badge
