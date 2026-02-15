# Product Strategy: Monetization, Roadmap & App Store Checklist

> **Process:** Items tagged `[MOCKUP]` require an HTML mockup (`ios/mockups/<feature>.html`) before implementation.

## 1. Monetization Recommendation

### Recommended: Freemium with Usage-Based Screenshot Limits

**Evaluation of Options:**

| Model | Pros | Cons | Verdict |
|-------|------|------|---------|
| Free with limits | Low friction, high downloads, covers costs | Needs IAP implementation | **RECOMMENDED** |
| Paid upfront ($4.99) | Simple, one-time revenue | Kills discoverability for niche app; needs brand recognition | Reject |
| Freemium subscription ($4.99/mo) | Recurring revenue, industry standard | Complex for solo dev; small, price-sensitive audience | Reject for v1 |
| Full subscription | Maximizes revenue per user | High churn risk for new unproven app | Reject for v1 |
| Ads + paid ad-free | Easy to implement | Destroys premium Solo Leveling aesthetic; kills immersion | Hard reject |

### Pricing Structure

| Tier | Price | Includes |
|------|-------|---------|
| Free | $0 | Manual logging, XP/ranks/quests/dungeons/achievements, HealthKit, friends, PRs, weekly reports. **3 screenshot scans/month free** |
| Screenshot Pack (consumable) | $1.99 | 20 additional scans |
| Screenshot Pack (consumable) | $3.99 | 50 additional scans |
| S-Rank Scanner (non-consumable) | $9.99 | Unlimited scans forever |

### Rationale
1. Core gamification loop costs nothing to serve -- all database operations
2. Screenshot feature is the only per-use marginal cost (~$0.01-0.05 per Claude API call)
3. 3 free scans/month lets every user try the feature
4. Solo Leveling audience skews 18-30 -- will download free apps but resist subscriptions
5. Lifetime $9.99 creates natural ceiling. At 200 lifetime screenshots, API cost is ~$2-10 vs $9.99 revenue

### Revenue Projection (Conservative)
- Month 1-3: 500 downloads, 5% conversion = 25 purchases at avg $5 = **$125**
- Month 6: 2,000 cumulative, 7% conversion = 140 purchases = **$700 cumulative**
- Year 1: 5,000 downloads, 8% conversion = 400 purchases = **~$2,500**
- Covers Railway hosting ($5-20/mo = $60-240/yr) and Claude API costs

### Implementation Complexity
Medium. StoreKit 2 in SwiftUI is straightforward. Requires backend `screenshot_count` field on user model + check in `/screenshot/process`. Estimated 2-3 days.

---

## 2. App Store Launch Checklist

### Apple Developer Program & Account
- [ ] Active Apple Developer Program membership ($99/year) -- team ID `D69T4MH7XQ` already in `project.yml`
- [ ] App ID registered (`com.nickchua.fitnessapp` per `project.yml`)
- [ ] HealthKit entitlement enabled in provisioning profile
- [ ] Distribution certificate and provisioning profiles created

### App Store Connect Configuration
- [ ] Create app record in App Store Connect
- [ ] Set pricing tier (Free with IAPs)
- [ ] Configure in-app purchases (screenshot packs) -- Phase 2
- [ ] Set app availability (countries/regions)

### App Metadata
- [ ] App name: "ARISE - Fitness Tracker" (check availability)
- [ ] Subtitle (30 chars): "Level Up Your Workouts"
- [ ] Description (4000 chars max): highlight Solo Leveling theme, screenshot scanning, gamification
- [ ] Keywords (100 chars): fitness,workout,tracker,gamification,solo leveling,gym,strength,RPG,XP
- [ ] Category: Primary = Health & Fitness, Secondary = Games (Role Playing)
- [ ] Support URL (required)
- [ ] Marketing URL (optional)

### App Icons
- [ ] 1024x1024 App Store icon -- **currently missing** (empty AppIcon.appiconset)
- [ ] Verify icon renders well at small sizes

### Screenshots
- [ ] 6.7" display (iPhone 15 Pro Max) -- minimum 3, recommend 5-8
- [ ] 6.5" display (iPhone 11 Pro Max) -- if supporting older devices
- [ ] 5.5" display (iPhone 8 Plus) -- if supporting older devices
- [ ] Consider app preview video (30s showing gamification loop)

### Legal & Privacy
- [ ] **Privacy Policy URL** -- REQUIRED (not yet created)
- [ ] **Terms of Service URL** -- strongly recommended
- [ ] App Privacy details in App Store Connect
- [ ] HealthKit usage descriptions (already in Info.plist)
- [ ] Photo Library usage description (already in Info.plist)

### Data Privacy Declarations (App Store Connect)
- [ ] HealthKit data (steps, calories, exercise time, stand hours)
- [ ] Email collection (authentication)
- [ ] Fitness/exercise data
- [ ] Photo library access (screenshots)
- [ ] Data linked to user identity

### Technical Requirements
- [ ] **Account deletion** -- REQUIRED. Not implemented.
- [ ] Remove `NSAllowsArbitraryLoads: true` from Info.plist
- [ ] Remove debug middleware and endpoints from production
- [ ] Restrict CORS from `"*"`
- [ ] Verify iOS 17.0 deployment target is acceptable
- [ ] Test on physical device
- [ ] Test with poor network connectivity
- [ ] Verify background/foreground behavior

### Export Compliance
- [ ] Encryption questionnaire (uses HTTPS + bcrypt -- "Yes, standard encryption")

### Age Rating
- [ ] Complete questionnaire (likely 4+, no objectionable content)

### TestFlight
- [ ] Upload build to TestFlight
- [ ] Internal testing (solo dev + friends)
- [ ] External beta (10-50 users) for 1-2 weeks before submission
- [ ] Collect crash reports and feedback

### App Review Preparation
- [ ] Demo account credentials for review team
- [ ] Review notes explaining screenshot feature (uses AI)
- [ ] Screenshots showing scanning workflow
- [ ] Ensure all features work without rate limiting during review

---

## 3. Launch Roadmap

### Phase 1: Must Ship (App Store Blockers) -- DONE

1. ~~**Account deletion endpoint + UI**~~ ✓
2. ~~**Privacy Policy**~~ ✓ (hosted on Railway at `/privacy`)
3. ~~**Remove `NSAllowsArbitraryLoads: true`**~~ ✓
4. **App icon** -- AppIcon.appiconset has image. Verify renders well at small sizes.
5. **App Store screenshots** -- Minimum 3 per device size.
6. ~~**Screenshot rate limiting**~~ ✓
7. ~~**Remove debug/dev artifacts**~~ ✓ (gated behind DEBUG)
8. **App Store Connect setup** -- Create app record, fill metadata, answer compliance questionnaires.
9. **TestFlight beta** -- Upload build, test on 3+ physical devices.
10. ~~**Token expiration fix**~~ ✓

### Phase 2: Fast Follow (2 Weeks Post-Launch)

1. `[MOCKUP]` **Monetization (StoreKit 2 IAPs)** -- Screenshot packs + lifetime unlock. Backend quota tracking, iOS paywall screen, App Store Connect IAP configuration. **Mockup:** `ios/mockups/paywall.html`

2. **Crash reporting** -- Sentry integration (free tier, 5K events/mo).

3. **Analytics** -- TelemetryDeck integration (free tier, 100K signals/mo).

4. **Keychain token storage** -- Migrate from UserDefaults.

5. `[MOCKUP]` **Onboarding flow** -- 3-screen "Awakening" walkthrough. **Mockup:** `ios/mockups/onboarding.html`

6. **App Store review prompt** -- `SKStoreReviewController` after 5th workout.

7. `[MOCKUP]` **Home UI refresh** -- ARISE 2.0 design (see designer plan). **Mockup:** `ios/mockups/home-v2.html`

### Phase 3: Post-Launch (Data-Driven)

1. `[MOCKUP]` Push notifications -- notification settings UI
2. `[MOCKUP]` Force update mechanism -- blocking modal
3. `[MOCKUP]` Data export -- settings screen addition
4. `[MOCKUP]` Offline mode / local caching -- connectivity banner
5. `[MOCKUP]` Widgets / Live Activities -- home screen widgets
6. `[MOCKUP]` Social sharing -- PR celebrations, rank-ups as shareable images
7. Accessibility audit
8. Subscription tier if usage warrants

---

## 4. Acceptance Criteria

### "Ready to Submit" Means:

1. All Phase 1 items complete and verified
2. Account deletion works end-to-end (confirmed with test account)
3. Privacy policy URL live and accessible
4. App icon renders correctly at all sizes
5. At least 3 App Store screenshots per required device size
6. `NSAllowsArbitraryLoads` removed, HTTPS still works
7. Debug endpoints/middleware removed or gated
8. TestFlight build tested on 2+ physical devices
9. No crashes during 30-minute smoke test (register, log workout, scan screenshot, view stats, add friend, quests/dungeons, profile, delete account)
10. App Review demo account prepared with pre-populated data
11. Screenshot rate limiting active
12. All App Store Connect metadata fields filled
13. Export compliance questionnaire answered

### Post-Launch Metrics to Track
- DAU / WAU
- Screenshot scans per day (alert if >100/day)
- User registrations per day
- Crash-free session rate (target: >99%)
- App Store rating (respond to all reviews)
- Claude API cost per day/week
- Conversion rate on screenshot IAPs (Phase 2)
- Retention: Day 1, Day 7, Day 30

### Cost Control Triggers

| Trigger | Action |
|---------|--------|
| Claude API > $50/month | Reduce free quota from 3/month to 1/month |
| Claude API > $100/month | Disable free tier; require IAP for any scans |
| Single user > 20 screenshots/day | Rate limit + investigate abuse |
| Railway > $30/month | Review DB size, implement archiving |
| Total costs > $200/month | Pause new registrations until monetization live |

### Emergency Kill Switch
Backend config flag `SCREENSHOT_PROCESSING_ENABLED` (defaults `True`). Set to `False` in Railway env vars to instantly disable all screenshot processing without a code deploy.

---

## 5. Key Tradeoffs

1. **Shipping without monetization in v1** -- Intentional. Getting live and gathering usage data is more valuable than delaying launch for IAPs. Rate limiting protects costs. Monetization follows in Phase 2 (2 weeks).

2. **Keeping UserDefaults for tokens in v1** -- Keychain is more secure, but UserDefaults works and won't cause rejection. Migrating mid-launch could log out existing beta users.

3. **No onboarding in v1** -- Solo Leveling theme is self-explanatory for target audience. Important for broader adoption but not a launch blocker.

4. **iOS 17+ deployment target** -- Cuts off devices older than iPhone XS (2018). Acceptable for target demographic (younger, tech-savvy).
