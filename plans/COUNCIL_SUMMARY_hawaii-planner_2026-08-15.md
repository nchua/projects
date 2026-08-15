# Council Summary — hawaii-planner ("Oahu Trip") — 2026-08-15

> Produced by a 4-agent council (Senior Staff Engineer, Product Designer, Product Manager, Oahu Domain Expert) with a cross-review round. **The canonical, full spec is `hawaii-planner/SPEC.md`** — this file is the persisted council summary for `/evaluate --against council` and `/pipeline`. Where the two disagree, SPEC.md wins.

## Objective

Collaborative family vacation-planner web app for the Aug 26–31, 2026 Oahu trip (5 travelers, one rental car, home base Aston Waikiki Beach Tower): realistic day-by-day schedules with drive times, geographically grouped activity ideas, and a restaurant suggest/rank/vote board with Yelp link-outs. Mobile-first, also great on desktop.

## Design (Designer, post-cross-review)

3 tabs (Itinerary | Ideas | Food) + header you-chip; full-screen name picker (no accounts or logins); signature "itinerary spine" timeline (stops = solid dots, drive legs = dashed 🚗 segments, home-base first row, computed "Back at hotel ~X PM" last row); no drag-drop — ••• menus + ▲▼ reorder mode; region-grouped idea pool with ≥3-idea cluster banners; ranked food board with first-class "Yelp ↗" buttons; unified `[👍 n][⭐ n]` reaction pill; empty-day "start from a day plan" templates; desktop three-pane cockpit; "trail map" high-contrast light theme with 9 region hues; strict mobile touch rules (delegated events, ≥44px, touch-action, :active states). Full detail: SPEC.md §UX.

## Technical Plan (Engineer, post-cross-review)

FastAPI + Postgres + SQLAlchemy + Alembic + vanilla-JS frontend served by the same app; mirrors fitness-app backend patterns and Caltrain's StaticFiles/monorepo-Railway precedent (Root Directory `hawaii-planner`, watch paths `hawaii-planner/**`). Data model: Member, Region (9 slugs + tour_order), DriveTime (symmetric upper-triangle + rush-hour display flags), Idea (kind activity|restaurant + reservation/closed-days/difficulty/best-time/meal-tags metadata + recommended_by), Vote (value interested|must_go; 3-star budget per member per board, 409 + swap payload), TripDay (nullable date, start/end times), ScheduleItem (position, duration/drive overrides, fixed_start_time pins, no stored computed times), AppState version for 10s polling. Pure backend timeline function (matrix + 10-min buffer, pin warnings + leave_by, return leg → overpacked, closed-day warnings). Bootstrap one-shot payload; mutations return recomputed day. `X-Trip-Token` middleware vs `LINK_TOKEN` env var. Full detail: SPEC.md §Architecture.

## Acceptance Criteria (PM)

Add-restaurant <30s on a phone; Yelp link or auto-search fallback on every restaurant; single-select reaction with server-enforced 3-star budget and friendly swap flow; pool pre-seeded (~30 activities, ~40 real family restaurant recs); drive chips + pins + late-arrival and overpacked warnings + total-drive display; cross-device visibility ≤20s, optimistic idempotent votes; one-handed at 375px, ≥44px targets, no horizontal scroll; cold load <3s; deployed on Railway.

## Test Plan

pytest on timeline (buffers, pins, return leg, closed days, overrides) and API (budget 409, idempotency, atomic reorder, bulk ordering, token 401); ruff before push; local SQLite browser walkthrough; real-iPhone pass; two-device sync check; deploy-watch after each push.

## Execution Order

P0 walking skeleton (deployed URL + name picker) → P1 schema + idempotent seed → **P2 boards + voting → ship link to family** → P3 itinerary builder (timeline tests first) → P4 polish. Commit per phase (`git commit -- hawaii-planner/`), `/ship` after execution.

## Execution Strategy

**Recommended: Single Agent** (tightly coupled greenfield; overlapping files) plus one parallel content-curation subagent producing `seed/*.json` (regions, matrix, activities, restaurants w/ Yelp URLs, day templates) during P0/P1.

## Risks & Open Questions

Static matrix vs rush hour (mitigated: flags, buffer, per-leg override, Maps link-outs); last-write-wins at 5 users (accepted; atomic reorder bounds it); booking urgency independent of the app (Kualoa/luaus book NOW, USS Arizona 56-day window passed → 3pm HST next-day batch, Hanauma T-2 7am HST, Diamond Head window open); verify Hanauma parking / Pali parking / Waimea Valley pricing at seed time; sunset + lunch-gap features deferred to v1.1.
