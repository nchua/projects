# Future Feature Ideas

## Gamification System (Partially Implemented)

**Status:** XP & Achievements implemented in Session 4. Quest system pending.

### Implemented
- XP & Leveling System (backend + iOS)
- Rank Progression (E → S)
- 18 Achievement badges
- XPRewardView component
- Achievement showcase in ProfileView

### TODO: Daily Quest System
**Priority: HIGH**

3 daily quests that refresh at midnight:
- "Complete 100 reps total" (25 XP)
- "Do 3 sets of a compound lift" (50 XP)
- "Log a workout under 45 minutes" (25 XP)

**Implementation:**
- `backend/app/models/quests.py` - Quest, UserQuest models
- `backend/app/services/quest_service.py` - Quest generation, progress tracking
- `backend/app/routers/quests.py` - GET /quests/, POST /quests/{id}/claim
- `ios/FitnessApp/Views/Home/QuestBoardView.swift` - Quest UI in HomeView

### TODO: Weekly Challenges
**Priority: HIGH**

Larger goals with bigger rewards:
- "Hit 50,000 lbs total volume" (200 XP)
- "Complete 4 workouts" (150 XP)
- "Try a new exercise" (100 XP)

### TODO: Streak System
**Priority: HIGH**

- Track consecutive workout days
- Visual streak counter on HomeView
- Streak protection (1 free pass per week)
- Milestone rewards (7-day: 150 XP, 30-day: 500 XP)
- "Don't break your streak!" notifications

### TODO: Urgent Quests
**Priority: MEDIUM**

Time-limited bonus challenges (e.g., "Complete a workout in the next 2 hours for 2x XP")

### TODO: Boss Battles
**Priority: LOW**

Monthly strength tests - hit specific weight targets for bonus XP

---

## WHOOP-Style Effort/Strain Tracking for Strength Growth

**Concept:** Track strength progression not just through PRs, but by analyzing effort relative to weight pushed.

**Problem it solves:**
- Some days you don't PR but you're still getting stronger
- If you lift the same weight with lower perceived effort (RPE), that indicates strength gains
- Current PR-only tracking misses these "hidden" gains

**Implementation ideas:**
- Create an effort matrix: Weight × Reps × RPE = Effort Score
- Track effort score over time for each exercise
- Show "efficiency gains" - same weight at lower RPE indicates progress
- Calculate a "strength efficiency ratio" similar to WHOOP's strain calculation
- Visualize: Weight pushed vs Effort trend (diverging lines = getting stronger)

**Metrics to track:**
- Volume (weight × reps × sets)
- RPE per set
- Calculated effort/strain score
- Recovery between sets (rest time)
- Session RPE vs actual volume pushed

**Visualization:**
- Matrix view: Exercise → Date → Weight/Effort ratio
- Trend line showing effort decreasing for same weights over time
- "Hidden PR" badges for efficiency improvements without weight PRs

**Reference:** WHOOP strain calculation methodology

---

## First-Time User Onboarding

**Concept:** Prompt new users to complete their profile before using the app.

**Why it's needed:**
- Strength percentiles require bodyweight to calculate bodyweight multipliers
- Age and sex affect strength standards comparisons
- Better personalized insights with complete profile data

**Implementation:**
- After first login, check if profile is incomplete (missing age, sex, bodyweight)
- Show onboarding wizard with screens for:
  1. Basic info (age, sex)
  2. Body metrics (height, weight)
  3. Training experience level
  4. Goal setting (optional)
- Allow "Skip" but show reminder badge on profile tab
- Store `hasCompletedOnboarding` flag in UserDefaults

---

## Apple Health Integration (HealthKit)

**Concept:** Import bodyweight and workout data from Apple Health automatically.

**Why it's needed:**
- Many users already track weight via smart scales synced to Health app
- Eliminates duplicate manual entry
- Provides more data points for accurate averages

**Implementation:**
- Request HealthKit authorization for body mass, workouts
- Import historical weight entries on first sync
- Set up background delivery for new weight entries
- Sync workout data (duration, calories) to Health app
- Show "Source: Apple Health" badge on imported entries

**Considerations:**
- Requires HealthKit capability in Xcode
- Need to handle permission denial gracefully
- Avoid duplicates when user logs manually and via Health

