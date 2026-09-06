# App Store Connect Metadata

Working drafts for every ASC text field, plus the privacy nutrition-label answer
sheet and the App Review notes. Companion to [`app-store-launch.md`](./app-store-launch.md).

> **`{APP_NAME}` is a placeholder.** The final name is deferred (launch checklist
> Phase 0.1). Search-and-replace it here, in `ios/project.yml`, and in the
> `/privacy` page in `backend/main.py` once it is locked.

---

## 1. Text fields

Character limits are hard caps enforced by ASC.

### Name — max 30
```
{APP_NAME}
```

### Subtitle — max 30
Appears under the name in search results. Carries real keyword weight.
```
Strength Training RPG
```
Alternatives: `Level Up Your Lifting` (21) · `Gamified Strength Tracker` (25)

### Promotional text — max 170
Editable **without** submitting a new build — the one field you can change any time.
Use it for what's new or seasonal, not evergreen copy.
```
Scan a screenshot from any gym app and your workout logs itself. Track e1RM,
break PRs, and climb from E-rank to the top. Your training, as a progression system.
```

### Keywords — max 100 chars, comma-separated, NO spaces after commas
Do not repeat words already in the name or subtitle — Apple indexes those
separately, so repeats waste characters.
```
gym,workout,lifting,strength,tracker,log,barbell,squat,bench,deadlift,pr,1rm,progress,rpg,level
```
(97 chars. Recount after any edit.)

### Description — max 4000
```
{APP_NAME} turns strength training into a progression system.

Every set you log is XP. Every PR moves your rank. Instead of a spreadsheet that
forgets you, you get a record that visibly levels up — from E-rank to the top.

SCAN INSTEAD OF TYPING
Point your camera roll at a screenshot from whatever app you already use. {APP_NAME}
reads the exercises, sets, reps, and weights and logs the whole session for you.
No re-entry, no lost workouts.

REAL STRENGTH MATH
- Estimated 1RM on every set, using the Epley formula
- Automatic PR detection across every lift
- Volume, intensity, and trend analysis over time
- Per-muscle-group breakdowns so you can see what you're actually training

KNOW WHEN TO PUSH
Connect Apple Health or WHOOP and {APP_NAME} factors recovery, HRV, resting heart
rate, and sleep into a readiness read — so you know when to go heavy and when the
smart move is to back off.

TRAIN WITH A PLAN
Follow structured campaigns with prescribed work, or log freely. Set strength goals
and watch the gap close week over week.

BRING FRIENDS
Add training partners, compare ranks, and keep each other honest.

PRIVACY
Your training data is yours. No ads, no tracking, no selling your health data to
anyone. Delete your account and everything with it, from inside the app, any time.

Screenshot scanning uses a credit system. New accounts get free scans every month,
and additional credits are available as an in-app purchase.
```

> **Copy review before submitting:** every claim above must be true of the build you
> ship. Guideline 2.3 rejections come from describing features the reviewer can't
> find. If campaigns or friends aren't user-reachable in v1.0, cut those sections.

### What's New — max 4000 (first release)
```
First release.
```

### URLs
| Field | Value | Status |
|---|---|---|
| Privacy Policy URL | `https://backend-production-e316.up.railway.app/privacy` | ✅ live (200) |
| Support URL | `https://backend-production-e316.up.railway.app/support` | ⚠️ written, not yet deployed |
| Marketing URL | — | optional |
| Terms of Service | `https://backend-production-e316.up.railway.app/terms` | ⚠️ written, not yet deployed |

`/support` and `/terms` were added to `backend/main.py` on 2026-09-06 alongside the
existing `/privacy` route. **They must be deployed to Railway before submission** —
`ios/scripts/preflight-appstore.sh` fails until all three return 200.

### Category
Primary: **Health & Fitness**. Secondary: consider **Sports** (optional).

---

## 2. Privacy nutrition label — answer sheet

ASC → App Privacy. **These answers must match `PrivacyInfo.xcprivacy` and the
`/privacy` page.** Apple cross-checks the manifest against the label, and a
mismatch stalls the submission.

For every row below: **Linked to user? Yes** (all rows are keyed to an account) ·
**Used for tracking? No** · **Purpose: App Functionality**.

| ASC data type | Why it's collected | Manifest key |
|---|---|---|
| Contact Info → Email Address | Registration and login | `…TypeEmailAddress` |
| Identifiers → User ID | Account id / username, friends and leaderboards | `…TypeUserID` |
| Health & Fitness → Health | Bodyweight, age, sex, height; WHOOP recovery/HRV/sleep | `…TypeHealth` |
| Health & Fitness → Fitness | Logged workouts, sets/reps/weights, steps, calories | `…TypeFitness` |
| User Content → Photos or Videos | Workout screenshots uploaded for AI extraction | `…TypePhotosorVideos` |
| User Content → Other User Content | Free-text session notes | `…TypeOtherUserContent` |

**Do not declare:** Location, Contacts, Browsing History, Search History, Purchase
History, Diagnostics, or Advertising Data. None are collected. There are no
third-party SDKs, so there is no vendor data collection to disclose.

**Answer "No" to "Do you use data for tracking?"** — `NSPrivacyTracking` is `false`
and there is no ATT prompt.

⚠️ If a future version adds analytics, crash reporting, or any SDK, all three
places must be updated together: `PrivacyInfo.xcprivacy`, this label, and `/privacy`.

---

## 3. App Review notes

Paste into ASC → App Review Information → Notes. **Fill in the credentials first.**

```
DEMO ACCOUNT
Email:    <fill in>
Password: <fill in>

The app is fully login-gated, so please use the account above. It is pre-loaded
with workout history so the progress, analytics, and personal-record screens are
populated, and it has unlimited scan credits so the screenshot importer can be
tested without hitting the paywall.

SCREENSHOT SCANNING (main feature)
Log tab -> Scan. Pick any screenshot of a workout from the photo library; the app
sends it to an AI vision model, extracts exercises/sets/reps/weights, and lets you
review and edit before saving. A few sample workout screenshots are saved in the
demo account's Photos library on request -- any gym-app screenshot works.

IN-APP PURCHASES
Scanning consumes credits. Free accounts get a monthly allowance; the paywall
appears when it runs out. Three products: two consumable credit packs and one
non-consumable unlimited unlock. The demo account already has unlimited access, so
to see the paywall, tap the credit counter in the Log tab.

APPLE HEALTH (optional)
HealthKit is used to read steps, calories, and activity, and to optionally write
completed strength workouts back to Health. The app is fully functional if you
decline the permission prompt -- nothing is gated behind it. Health data is used
only to show the user their own stats. It is never used for advertising and is
never shared or sold.

WHOOP (optional)
An optional OAuth connection that reads recovery, HRV, resting heart rate, and
sleep to inform a training-readiness score. Not required to use the app, and not
needed to review it.

ACCOUNT DELETION
Profile tab -> Delete Account. Requires password confirmation. The account becomes
inaccessible immediately and all data is permanently purged after 30 days.
```

---

## 4. Screenshot plan

Screenshots must be captured from the real running app. Mockups, marketing renders,
and device frames containing non-app content risk a 2.3 rejection.

**Required:** iPhone 6.9" set. **Also required if iPad support is kept** (see launch
checklist Phase 0.3): iPad 13" set. Confirm exact pixel dimensions in ASC at upload —
Apple revises them. Capture on the installed simulators: **iPhone 17 Pro Max** (6.9")
and **iPhone Air**.

Up to 10 slots; 3–5 well-chosen ones beat 10 filler. Proposed order — the first two
are what most users actually see in search results, so they carry the pitch:

| # | Screen | What it has to prove |
|---|---|---|
| 1 | Home / Status | The identity: rank, level, XP. This is the hook. |
| 2 | Screenshot scan → extracted result | The "logs itself" claim, made concrete |
| 3 | Progress / e1RM trend chart | Real strength math, populated with real history |
| 4 | Personal records | Payoff and progression |
| 5 | Readiness / recovery | The Health + WHOOP differentiator |

Capture against the demo account so every screen is populated — empty states are
the most common way screenshots undersell an app.

Simulator capture:
```bash
xcrun simctl boot "iPhone 17 Pro Max"
xcrun simctl io booted screenshot ~/Desktop/shot-01.png
```
Status bar cleanup (full battery, clean time) is optional but looks deliberate:
```bash
xcrun simctl status_bar booted override --time "9:41" --batteryLevel 100 --cellularBars 4
```
