# ARISE Fitness App -- App Store Launch Overview

## Quick Links

| Plan | File | Focus |
|------|------|-------|
| Technical Analysis | `01-engineer-technical-analysis.md` | Cost control, analytics, missing features, security |
| Product Strategy | `02-pm-monetization-and-roadmap.md` | Monetization, App Store checklist, launch roadmap |
| Design Refresh | `03-designer-ui-refresh.md` | Home/quest UI modernization, onboarding |

---

## Executive Summary

Three council agents (Engineer, PM, Designer) analyzed the codebase and produced aligned recommendations for App Store launch.

### Key Decisions Made

1. **Monetization:** Freemium with usage-based screenshot limits. Free core app + screenshot packs ($1.99-$3.99) + lifetime unlimited ($9.99).

2. **Screenshot cost control:** Server-side rate limiting (10/day, 100/month free), usage tracking table, emergency kill switch, graceful 429 handling in iOS.

3. **UI refresh direction:** "ARISE 2.0 -- Minimal Void." Unify design system (sunset legacy 4px corners), reduce home sections from 9 to 6, add floating action button, replace emojis with SF Symbols.

4. **Analytics stack:** TelemetryDeck (privacy-first, no ATT needed) + Sentry (crash reporting).

5. **Missing features priority:** Account deletion and privacy policy are hard App Store blockers. Onboarding, push notifications, and review prompts are fast-follow.

---

## Process Rule: HTML Mockups for UI Changes

**Before implementing any item that changes the user-facing UI, create an HTML mockup first** (`ios/mockups/<feature-name>.html`). Get approval on the mockup before writing Swift code. Items requiring mockups are tagged with `[MOCKUP]` below.

---

## Launch Roadmap Summary

### Phase 1: Must Ship (App Store Blockers) -- DONE
1. ~~Account deletion (backend + iOS)~~ ✓
2. ~~Privacy policy (host + link in app)~~ ✓
3. ~~PrivacyInfo.xcprivacy manifest~~ ✓
4. ~~Remove NSAllowsArbitraryLoads~~ ✓
5. ~~Remove debug artifacts, restrict CORS~~ ✓
6. ~~Screenshot rate limiting + kill switch~~ ✓
7. ~~Security: token expiration (30 days -> 60 min)~~ ✓
8. App icon (1024x1024)
9. App Store screenshots
10. App Store Connect setup
11. TestFlight beta

### Phase 2: Fast Follow (2 weeks post-launch)
1. `[MOCKUP]` StoreKit 2 IAPs (monetization) -- paywall screen
2. TelemetryDeck + Sentry (analytics + crashes)
3. Keychain token storage
4. `[MOCKUP]` Onboarding flow -- 3-screen "Awakening" walkthrough
5. App Store review prompt
6. `[MOCKUP]` Home UI refresh (ARISE 2.0) -- full home screen redesign

### Phase 3: Post-Launch (data-driven)
1. `[MOCKUP]` Push notifications -- notification settings UI
2. `[MOCKUP]` Force update mechanism -- blocking modal
3. `[MOCKUP]` Data export -- settings screen addition
4. `[MOCKUP]` Offline mode -- connectivity banner
5. `[MOCKUP]` Widgets -- home screen widgets
6. `[MOCKUP]` Social sharing -- share cards
7. Accessibility

---

## Cost Control Triggers

| Trigger | Action |
|---------|--------|
| Claude API > $50/mo | Reduce free quota 3/mo -> 1/mo |
| Claude API > $100/mo | Disable free tier entirely |
| Single user > 20/day | Rate limit + investigate |
| Total costs > $200/mo | Pause registrations until monetization live |

---

## Open Questions

1. **App name:** "Fitness Tracker" (Info.plist) vs "ARISE" (UI)?
2. **Account deletion:** 30-day grace period or immediate?
3. **Privacy policy hosting:** Personal website, GitHub Pages, or Railway?
4. **Screenshot free quota:** 3/month (PM) vs 10/day (Engineer) for v1?
5. **Push notifications:** Phase 2 or Phase 3?
