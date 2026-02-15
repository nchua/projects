# Technical Analysis: App Store Readiness

> **Process:** Items tagged `[MOCKUP]` require an HTML mockup (`ios/mockups/<feature>.html`) before implementation.

## 1. Screenshot API Cost Control -- DONE

### Current Flow
- `/screenshot/process` (single) and `/screenshot/process/batch` (up to 10) endpoints in `backend/app/api/screenshot.py`
- Each screenshot triggers one `client.messages.create()` call to `claude-sonnet-4-20250514` with `max_tokens=2000` in `backend/app/services/screenshot_service.py:302-304`
- The extraction prompt is ~125 lines (~1,200-1,500 tokens)
- **Zero rate limiting, zero per-user usage tracking, zero cost tracking**

### Cost Estimate Per Screenshot Call
- Claude Sonnet image input: typical phone screenshot (1170x2532 pixels) ~ 1,600-2,000 input tokens
- Prompt text: ~1,300 input tokens
- Total input per call: ~3,000-3,500 tokens
- Output: structured JSON, typically 500-1,500 tokens (max capped at 2,000)
- Anthropic API pricing (Sonnet): ~$3/M input, ~$15/M output
- **Estimated cost per screenshot: $0.01 - $0.03**
- **Batch of 10 screenshots: $0.10 - $0.30**
- Heavy user (5 screenshots/day) = ~$1.50-4.50/month per user
- At 1,000 DAU doing 2 screenshots/day = **$600-1,800/month**

### Proposed Rate Limiting Strategy

**Step 1: New `ScreenshotUsage` model** (new table):
```python
class ScreenshotUsage(Base):
    __tablename__ = "screenshot_usage"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    screenshots_count = Column(Integer, default=1)  # batch count
    estimated_cost = Column(Float)
```

**Step 2: Rate-limit check** at start of both `/process` and `/process/batch`:
- Free tier: 10 screenshots/day, 100/month
- Query: `SELECT COUNT(*) FROM screenshot_usage WHERE user_id = ? AND created_at > ?`
- Return `HTTP 429 Too Many Requests` with JSON: `{"detail": "Daily screenshot limit reached", "limit": 10, "used": 10, "resets_at": "2026-02-15T00:00:00Z"}`

**Step 3: Cooldown** -- 10-second minimum gap between submissions per user

**Step 4: iOS graceful degradation** in `ScreenshotProcessingViewModel.swift`:
- Catch `HTTP 429`, parse response
- Show: "You've used all 10 screenshots today. Resets at midnight."
- Offer manual workout logging as fallback

**Step 5: Emergency kill switch** -- `SCREENSHOT_PROCESSING_ENABLED` env var on Railway. Set to `False` to instantly disable all processing without a code deploy.

### Files to Modify
- `backend/app/models/` -- new `screenshot_usage.py`
- `backend/app/api/screenshot.py:43-50` and `:236-243` -- rate limit check
- `ios/FitnessApp/Views/Log/ScreenshotProcessingViewModel.swift` -- handle 429
- `ios/FitnessApp/Services/APIClient.swift:508-521` -- 429 case in screenshot response

---

## 2. Analytics & Crash Reporting

### Current State
Zero analytics or crash reporting SDKs. Confirmed by searching for Firebase, Amplitude, Sentry, PostHog, Crashlytics, TelemetryDeck -- none found.

### Recommended: TelemetryDeck (analytics) + Sentry (crashes)

**Why TelemetryDeck over Firebase/Amplitude:**
- Privacy-first: no user tracking, GDPR/ATT compliant by design
- No ATT prompt needed (uses differential privacy)
- SwiftUI-native, lightweight (~100KB), SPM-compatible
- Free tier: 100K signals/month
- Solo developer friendly

**Why Sentry over Crashlytics:**
- No Firebase dependency (Crashlytics requires Firebase Core + GoogleUtilities)
- Better Swift/SwiftUI crash symbolication
- Error breadcrumbs (tracks actions leading to crash)
- Free tier: 5K errors/month

### Key Events to Track

**Screen views** (automatic with TelemetryDeck):
- home, quests, dungeons, friends, stats, profile, log, history
- `auth_login`, `auth_register`, `auth_logout`

**Feature usage:**
- `screenshot_processed` (type: gym_workout|whoop_activity, confidence: high|medium|low)
- `workout_logged` (source: manual|screenshot)
- `quest_completed`, `quest_claimed`
- `dungeon_accepted`, `dungeon_completed`, `dungeon_abandoned`
- `friend_request_sent`, `friend_request_accepted`
- `goal_created`, `mission_accepted`, `mission_declined`
- `bodyweight_logged`, `pr_achieved`

**Error/performance:**
- `api_error` (endpoint, status_code)
- `screenshot_failed` (error_type)

### Integration Points

1. `ios/project.yml` -- Add SPM dependencies
2. `ios/FitnessApp/FitnessApp.swift` -- Initialize SDKs in `init()`
3. `ios/FitnessApp/Services/APIClient.swift:633` -- Sentry breadcrumb in `request()` method
4. `ios/FitnessApp/Views/Log/ScreenshotProcessingViewModel.swift` -- Track screenshot events
5. New: `ios/FitnessApp/Services/AnalyticsService.swift` -- Central analytics facade

### Privacy Compliance
- TelemetryDeck: "Analytics - Not Linked to User" in App Store Connect
- Sentry: "Crash Data - Not Linked to User"
- No GDPR consent banner needed for anonymous analytics
- Include note in Privacy Policy

---

## 3. Missing Features Audit

### MUST-HAVE for App Store Launch

**3.1 Privacy Policy & Terms of Service** -- ✓ DONE

**3.2 Account Deletion** -- ✓ DONE

**3.3 PrivacyInfo.xcprivacy Manifest** -- ✓ DONE

**3.4 Remove NSAllowsArbitraryLoads** -- ✓ DONE

### SHOULD-HAVE for Launch

**3.5 Onboarding Flow** `[MOCKUP]`
- Effort: **Medium** (1-2 days)
- 3-4 screens: Welcome, Screenshot demo, Gamification explainer, HealthKit permission
- Track `hasCompletedOnboarding` in UserDefaults
- New file: `ios/FitnessApp/Views/Onboarding/OnboardingView.swift`
- **Mockup first:** `ios/mockups/onboarding.html`

**3.6 Push Notifications**
- Effort: **Large** (2-3 days)
- Key notifications: quest reset, dungeon spawn, friend request, streak at risk, weekly report
- Requires: APNs certificate/key, backend push service, device token registration endpoint

**3.7 App Store Review Prompt**
- Effort: **Small** (1 hour)
- `AppStore.requestReview(in:)` after 5th workout or first PR
- Apple rate-limits to 3 times per 365 days automatically

**3.8 Data Export** `[MOCKUP]`
- Effort: **Medium**
- Backend: `GET /auth/export-data` -- JSON with all user data
- iOS: "Export My Data" in settings + share sheet
- **Mockup first:** `ios/mockups/data-export.html`

**3.9 Offline Handling** `[MOCKUP]`
- Effort: **Medium**
- `NWPathMonitor` for network status
- Persistent "No connection" banner in MainTabView
- Cache last-loaded home data
- **Mockup first:** `ios/mockups/offline-banner.html`

### NICE-TO-HAVE (Post-Launch)

- Force update mechanism (`/version/check` endpoint)
- Deep linking / Universal links
- Accessibility (zero `accessibilityLabel` modifiers currently)
- Localization (all strings hardcoded English)

---

## 4. Security Hardening

### 4.1 CORS Allows All Origins -- ✓ DONE (restricted to Railway domain)

### 4.2 Access Token 30 Days -- ✓ DONE (60 min access, 30 day refresh)

### 4.3 JWT Tokens in UserDefaults -- Not Keychain
- File: `ios/FitnessApp/Services/APIClient.swift:14-22`
- Tokens stored in plaintext plist. Accessible via backups/jailbreak.
- Fix: Migrate to Keychain using `Security` framework

### 4.4 Debug Endpoint Exposed -- ✓ DONE (gated behind DEBUG)

### 4.5 Debug Middleware Logging Everything -- ✓ DONE (gated behind DEBUG)

### 4.6 Default Secret Key
- File: `backend/app/core/config.py:19`
- Default: `"your-secret-key-here-change-in-production"`
- Fix: Add startup check -- refuse to start if default key in production

### 4.7 Verbose Error Messages -- ✓ DONE (generic message in production)

### 4.8 File Upload Size Race Condition
- File: `backend/app/api/screenshot.py:90-98`
- File fully read into memory before size validation
- Fix: Set `--limit-request-body` on uvicorn or read in chunks

---

## Open Technical Questions

1. What should the free tier screenshot limits be? (10/day for cost protection vs 3/month for monetization)
2. Account deletion grace period: 30-day recovery window or immediate hard delete?
3. App name: "Fitness Tracker" (Info.plist) vs "ARISE" (UI theme)?
4. `passlib[bcrypt]` in requirements.txt is unused (code imports `bcrypt` directly). Dead dependency.
5. `UIBackgroundModes` includes `fetch` and `processing` but no background task code exists. Apple may flag.
