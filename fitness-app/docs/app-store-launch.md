# App Store Launch Checklist

**Target:** direct App Store submission (no TestFlight beta phase).
**Team ID:** `D69T4MH7XQ` · **Bundle ID:** `com.nickchua.fitnessapp`
**Audit date:** 2026-09-06 (Xcode 26.2, iOS 17.0 deployment target)

Ordered by lead time, not by effort. Phase 1 has multi-day waits that block
everything downstream — start it before writing a single line of marketing copy.

---

## Where we stand

Verified by inspection on the audit date, not assumed:

| Gate | Status | Notes |
|---|---|---|
| Apple Developer Program membership | ✅ | `DEVELOPMENT_TEAM = D69T4MH7XQ` resolves |
| Release archive builds clean | ✅ | `** ARCHIVE SUCCEEDED **`, 2 benign warnings |
| App icon (1024×1024, no alpha) | ✅ | `Assets.xcassets/AppIcon.appiconset` |
| Account deletion in-app | ✅ | `HunterView.swift:210` → `APIClient.deleteAccount` — Apple requires this for any app with account creation |
| Privacy policy live + reachable | ✅ | `GET /privacy` → 200 |
| Terms of service | ✅ *(deployed 2026-09-06)* | `GET /terms` → 200 in production |
| Preflight check script | ✅ *(added 2026-09-06)* | `bash ios/scripts/preflight-appstore.sh` |
| Restore Purchases in UI | ✅ | `ScanPaywallView.swift:135` — required for non-consumable `scan_unlimited` |
| Terms + privacy links on paywall | ✅ | `ScanPaywallView.swift:143,149` |
| Privacy manifest present + bundled | ✅ | `PrivacyInfo.xcprivacy` confirmed inside `.app` |
| Privacy manifest **accurate** | ✅ *(fixed 2026-09-06)* | Declared zero collected data types while the app collects email, health, fitness, photos. Now matches `/privacy` |
| Export compliance declared | ✅ *(fixed 2026-09-06)* | `ITSAppUsesNonExemptEncryption: false` |
| Production APNs entitlement | ✅ *(fixed 2026-09-06)* | Release now uses `FitnessAppRelease.entitlements` (`aps-environment: production`) |
| Sign in with Apple | ➖ N/A | Email/password only, no third-party login — so SIWA is not required |
| Third-party SDK privacy manifests | ➖ N/A | Zero SPM/CocoaPods dependencies |
| **Paid Applications Agreement** | ❌ **BLOCKER** | Phase 1 — no IAP can be sold or even tested without it |
| **IAP products created in ASC** | ❌ **BLOCKER** | Phase 2 — three SKUs exist in code only |
| **App Store Connect app record** | ❌ **BLOCKER** | Phase 1 |
| **Screenshots** | ❌ **BLOCKER** | Phase 4 |
| **App Review demo account** | ⚠️ *(script ready 2026-09-06)* | `backend/scripts/seed_review_account.py` + tests. **Run it against prod, then paste the credentials into ASC** (Phase 5) |
| Support URL | ✅ *(deployed 2026-09-06)* | `GET /support` → 200 in production; preflight checks it |
| Anthropic spend ceiling | ✅ *(added 2026-09-06)* | `ANTHROPIC_DAILY_CALL_CEILING` (default 500 calls/day, owner warned at 80%) — over it scans 503 and debit nothing. **Set the number from real usage** |
| Auth rate limits | ✅ *(password-reset added 2026-09-06)* | login 5/10min, register 20/10min, password-reset request 10/10min — all per client IP |
| Final app name | ❌ | Phase 0 — deferred by decision, but blocks the ASC record |
| iPad scope | ✅ *(decided 2026-09-06)* | iPhone only — one screenshot set, no iPad layout risk |

---

## Phase 0 — Decisions to lock

### 0.1 App name  *(deferred — revisit before Phase 1)*

The project is internally inconsistent: `CFBundleDisplayName` is **"Fitness Tracker"**
while every string, the privacy policy, and the design system say **"ARISE"**.
Whatever wins, it has to be applied in all four places:

- `ios/project.yml` → `INFOPLIST_KEY_CFBundleDisplayName` and `info.properties.CFBundleDisplayName`
- `backend/main.py` → the `/privacy` page title and body
- App Store Connect app name (30 char limit) + subtitle (30 char limit)
- The `NSHealth*`/`NSPhotoLibrary` usage strings (they already say "Arise")

Constraints worth knowing before picking:
- App Store names must be unique. "Arise" is a common word — assume it is taken and
  have a fallback ready. Uniqueness is only confirmable by trying to reserve it in ASC.
- Reserving a name in ASC holds it; you do not have to ship immediately.

### 0.2 Solo Leveling IP exposure

The app is Solo Leveling–*inspired*, which is fine. Two specifics are not:

- **`Colors.swift:254` — S-rank titled "Shadow Monarch".** This is a distinctive
  proper noun from the series and it is user-facing. Rename it.
- Grep for other direct lifts before submitting. Generic RPG vocabulary
  (rank, level, XP, gate, hunt) is not a problem; named entities are.

This is a rejection *and* a takedown risk, and it is cheap to avoid.

### 0.3 iPad — DECIDED 2026-09-06: iPhone only ✅

`TARGETED_DEVICE_FAMILY` is now `"1"`. There was no iPad-conditional code in the
app, so nothing had to be unwound. This removes the iPad screenshot set, the iPad
orientation obligations, and a class of layout rejections. The
"All interface orientations must be supported" build warning is gone as a result.

iPad can be added back in a later version if it becomes a real use case.

### 0.4 IAP pricing

Three SKUs are hardcoded in `StoreKitManager.swift` and seeded in
`entitlement_service.py`. Prices are not set anywhere yet — they come from ASC:

| Product ID | Type | Effect |
|---|---|---|
| `com.nickchua.fitnessapp.scan_20` | Consumable | +20 scan credits |
| `com.nickchua.fitnessapp.scan_50` | Consumable | +50 scan credits |
| `com.nickchua.fitnessapp.scan_unlimited` | **Non-consumable** | Unlimited scans entitlement |

Sanity-check the unit economics before pricing: every scan is an Anthropic Claude
Vision call you pay for. `scan_unlimited` is a one-time purchase against an
unbounded recurring cost — model the worst case, or reconsider it as a
subscription. See Phase 6.

---

## Phase 1 — App Store Connect setup  *(start first: multi-day lead time)*

- [ ] **Sign the Paid Applications Agreement.** ASC → Business. Requires tax forms
      (W-9 for US) and banking details. **Nothing IAP-related works until this is
      active — not even sandbox testing.** This is the single longest pole; it can
      take several business days.
- [ ] Register the bundle ID `com.nickchua.fitnessapp` in the Developer portal with
      HealthKit, In-App Purchase, and Push Notifications capabilities enabled.
      (Automatic signing may have created it already — verify, don't assume.)
- [ ] Create the app record in ASC once the name is locked (Phase 0.1).
- [ ] Create an APNs key (.p8) for production push, if not already done, and confirm
      the backend is configured with it.

## Phase 2 — In-app purchases

- [ ] Create all three products in ASC using the **exact** IDs above. A typo means
      `Product.products(for:)` silently returns fewer products and the paywall
      renders empty.
- [ ] Set the type correctly: `scan_20`/`scan_50` = **Consumable**,
      `scan_unlimited` = **Non-consumable**. This cannot be changed after creation.
- [ ] Set prices per Phase 0.4.
- [ ] Write display name + description for each (reviewer-visible).
- [ ] Upload a **review screenshot for each product** — a required field, and a
      common cause of "Missing Metadata" limbo.
- [ ] Attach all three to the first version so they review together. IAPs submitted
      separately from the binary get reviewed separately and can lag.
- [ ] Test the full purchase → `verify-purchase` → credit flow in Sandbox on a real
      device, including **Restore Purchases** on a second device.

## Phase 3 — Build & upload

- [ ] Set the version/build for release. `CFBundleShortVersionString` is `1.0`,
      `CFBundleVersion` is `1` — both live in `ios/project.yml` (`info.properties`),
      not in `Info.plist`, which xcodegen regenerates.
      **Every upload needs a unique, increasing `CFBundleVersion`.**
- [ ] `bash ios/scripts/preflight-appstore.sh` — must pass clean.
- [ ] `xcodegen generate` then Archive in Xcode (Product → Archive, Release config).
- [ ] Distribute → App Store Connect → Upload.
- [ ] Confirm in ASC that the build shows **no** export-compliance prompt (proves
      `ITSAppUsesNonExemptEncryption` took effect).
- [ ] After the first upload, verify a **production** push actually arrives on a
      real device. This is what the Debug/Release entitlements split is protecting.

## Phase 4 — Metadata & assets

Draft copy, keywords, and the privacy nutrition-label answers live in
[`app-store-metadata.md`](./app-store-metadata.md).

- [ ] **Screenshots.** iPhone 6.9" is the only required set. Confirm exact pixel dimensions in ASC at upload time — Apple changes them.
      Capture on the simulators already installed (iPhone 17 Pro Max / iPhone Air).
      iPad set is **not** needed — iPhone-only was decided in Phase 0.3.
      Screenshots must show the *actual* app, not mockups or marketing renders.
- [ ] Name (30), subtitle (30), promotional text (170), description (4000),
      keywords (100, comma-separated, no spaces).
- [ ] **Support URL** — required. `https://backend-production-e316.up.railway.app/support`
      (deployed 2026-09-06; preflight verifies it returns 200).
- [ ] Marketing URL — optional.
- [ ] License agreement: keep Apple's standard EULA (the paywall already links it).
      `GET /terms` covers the hosted service around it — accounts, data, purchases.
- [ ] Privacy policy URL: `https://backend-production-e316.up.railway.app/privacy`
      (swap for a custom domain if the name changes — the URL is user-visible).
- [ ] Age rating questionnaire.
- [ ] Privacy nutrition label — must match `PrivacyInfo.xcprivacy` and `/privacy`.
      Answer sheet is in `app-store-metadata.md`; they are checked against each other.
- [ ] Category: Health & Fitness. Confirm the secondary category.

## Phase 5 — Review readiness

- [ ] **Create a demo account and put it in App Review Notes.** The app is fully
      login-gated. No credentials → automatic rejection under Guideline 2.1.
      Seed it with real-looking workout history so the reviewer sees a populated
      app rather than empty states, and give it unlimited scans so screenshot
      processing can be exercised without hitting the credit wall.
      Script (2026-09-06): from `backend/`,
      `SEED_USER_EMAIL=… SEED_USER_PASSWORD=… venv/bin/python scripts/seed_review_account.py`
      — ten weeks ending yesterday through the real ingest path; idempotent.
- [ ] **Give the demo account a working HealthKit story.** A reviewer on a fresh
      simulator/device has no Health data. Note in Review Notes that HealthKit is
      optional and the app is fully functional without granting it.
- [ ] Write App Review Notes covering: demo credentials, that scans cost credits and
      how to trigger the paywall, and that WHOOP is optional OAuth.
- [ ] Set contact info for the review team.

### Known rejection risks for *this* app

1. **Guideline 2.1 — no demo account.** Highest-probability rejection. See above.
2. **Guideline 3.1.1 — IAP.** Restore Purchases exists ✅ and terms/privacy are
   linked ✅. Verify prices render from StoreKit (never hardcode a price string)
   and that the paywall degrades gracefully if `loadProducts()` returns empty.
3. **Guideline 5.1.1 — HealthKit.** HealthKit data must not be used for advertising
   or sold, and the usage strings must be specific. Current strings are good.
   HealthKit apps also **must** have a privacy policy — ✅.
4. **Guideline 5.1.1(v) — account deletion.** ✅ implemented. Confirm it is easy to
   find (Profile → it's there) and actually completes.
5. **Guideline 4.2 — minimum functionality.** Not a concern; the app is substantial.
6. **IP / Guideline 5.2.** See Phase 0.2 — "Shadow Monarch".
7. **Guideline 1.1.6 / 2.3 — accurate metadata.** Screenshots must be real app UI.

## Phase 6 — Backend production readiness

The backend stops being "my app" the moment it is public. Worth a hard look:

- [x] **Anthropic API cost ceiling.** *(2026-09-06)* `ANTHROPIC_DAILY_CALL_CEILING`
      bounds aggregate vision calls per UTC day across all users (spec §G4.1):
      over it both scan endpoints 503 without debiting a credit, and the owner
      is emailed once at the warn threshold and once at the cap. Default is a
      generous 500/day — **set it from real usage**. `scan_unlimited` remains a
      one-time payment against a recurring cost; the ceiling bounds the blast radius.
- [ ] **Close the IAP verification hole.** `verify-purchase` currently trusts the
      client's `transaction_id` (documented at `app/api/scan_balance.py:1-14`);
      `StoreKitManager` passes `signedTransaction: nil`. The interim caps bound the
      damage but a determined user can mint credits. Verifying the StoreKit 2 JWS
      server-side is the real fix. **Acceptable to launch with the caps; track it.**
- [x] Rate limiting on auth endpoints (registration, login, password reset). *(password-reset request limit added 2026-09-06)*
- [ ] Confirm `alembic upgrade head` is clean and prod schema matches (there's a
      known history of stamp drift — check, don't assume).
- [ ] Error monitoring / alerting for a user base that isn't you.
- [ ] A real, monitored support email. `/privacy` currently advertises
      `privacy@arise-fitness.app` — confirm that domain exists and receives mail,
      or change it. A dead contact address on a published privacy policy is bad.

---

## After submission

- [ ] Watch for the review outcome; typical turnaround is 24–48h.
- [ ] Have the "Rejected → fix → resubmit" loop ready; a first-submission rejection
      is normal, not a failure.
- [ ] Decide on phased release vs. immediate availability.
- [ ] Confirm the production build's push notifications, IAP, and screenshot
      processing all work against the live backend **after** release — sandbox
      passing does not prove production works.
