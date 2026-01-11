# Fitness App Gamification Enhancement Plan

## Overview

Comprehensive plan to enhance the Solo Leveling-inspired fitness app with a full RPG experience: meaningful stats, expanded HealthKit, celebrations, shop, challenges, and social features.

**Created:** January 2026

---

## Progress Log

### Session: January 10, 2026

#### Completed
- [x] **Fixed iOS/backend rank threshold mismatch** - Synced `HunterRank.minLevel` and `forLevel()` in `Colors.swift` to match backend values (E:1, D:11, C:26, B:46, A:71, S:91)

- [x] **Phase 1: Visual Celebrations (Partial)**
  - Created `RankUpCelebrationView.swift` - Full-screen dramatic animation with:
    - "RANK UP!" header with rank-color glow
    - Old → New rank badge transition with arrow
    - Pulsing glow effect behind new badge
    - Fantasy title reveal (e.g., "YOU ARE NOW A ELITE")
    - Staggered animation sequence (~2.5 seconds)
  - Created `PRCelebrationView.swift` - Compact overlay with gold shimmer (ready for integration)
  - Integrated rank-up celebration into `LogView.swift` workout completion flow
  - Added DEBUG mode: Long-press (2s) on idle quest view triggers test celebration
  - **Tested successfully in simulator** - C→B rank-up working with all animations

---

### Session: January 10, 2026 (Continued)

#### Completed
- [x] **Phase 1: PR Celebration Integration (COMPLETE)**
  - Backend: Added `PRAchieved` model to `schemas/workout.py`
  - Backend: Added `prs_achieved: List[PRAchieved]` to `WorkoutCreateResponse`
  - Backend: Modified `workouts.py` to detect and return PR details with exercise names
  - iOS: Added `PRAchievedResponse` struct to `APITypes.swift`
  - iOS: Updated `PRCelebrationView` with optional counter badge ("1 of N PRs")
  - iOS: Added PR celebration chain to `LogView.swift` (shows before rank-up)
  - Full celebration sequence now: PRs (sequential) → Rank-up → XP Reward
  - **Deployed to Railway**

#### Commits
- `7686ee7` - Add PR celebration to workout completion flow

#### Files Modified
| File | Action | Description |
|------|--------|-------------|
| `backend/app/schemas/workout.py` | Modified | Added `PRAchieved` model + field to response |
| `backend/app/api/workouts.py` | Modified | Query PRs with exercise details, build response |
| `ios/.../Services/APITypes.swift` | Modified | Added `PRAchievedResponse` struct |
| `ios/.../Components/PRCelebrationView.swift` | Modified | Added counter badge params |
| `ios/.../Views/Log/LogView.swift` | Modified | Added PR celebration chain |

---

### Session: January 10, 2026 (Earlier)

#### Commits
- `18878b8` - Fix numeric input deletion and add keyboard dismissal
- `ae15f36` - Add gamification enhancement roadmap
- `faa18b3` - Add Phase 1 celebration views
- `b4b55b4` - Fix Equatable issue and add debug mode for testing

#### Files Created/Modified
| File | Action | Description |
|------|--------|-------------|
| `ios/.../Components/RankUpCelebrationView.swift` | Created | Full-screen rank-up animation |
| `ios/.../Components/PRCelebrationView.swift` | Created | PR celebration overlay (not yet integrated) |
| `ios/.../Views/Log/LogView.swift` | Modified | Added celebration chain + debug mode |
| `ios/.../Utils/Colors.swift` | Modified | Fixed rank thresholds |
| `GAMIFICATION_PLAN.md` | Created | This roadmap |
| `QUICK_START.md` | Modified | Added lessons learned (#6, #7) |

---

### Next Steps

#### Phase 1: COMPLETE
- [x] **Integrate PR celebration** - Backend returns `prs_achieved` in `WorkoutCreateResponse`
  - Added `PRAchieved` model to backend schemas
  - Added `prs_achieved` field to workout creation response
  - PRCelebrationView integrated with sequential display + "1 of N" counter
  - Full chain: PRs → Rank-up → XP Reward
- [x] **Level-up animation** - Already working in `XPRewardView` (counter animation, XP bar fill, level display)

#### Phase 2: HealthKit Expansion
- [ ] Add sleep data (hours, quality stages) to `HealthKitManager.swift`
- [ ] Add HRV and resting heart rate
- [ ] Add auto-workout detection from Apple Watch
- [ ] Add bodyweight sync from smart scales
- [ ] Update backend `DailyActivity` model with new fields

#### Phase 3: Stats System (After Phase 2)
- [ ] Design stat calculation formulas
- [ ] Create `HunterStats` backend model
- [ ] Build `StatHexagonView.swift` radar chart
- [ ] Integrate into profile screen

---

## The Six Hunter Stats

| Stat | Name | Calculation | Source |
|------|------|-------------|--------|
| **PWR** | Power | Weighted e1RM of Big Three (Squat 35%, Bench 30%, Deadlift 35%) | PR data |
| **VOL** | Volume | 4-week rolling average weekly volume (lbs) | Workout sets |
| **DEN** | Density | Work per minute (volume / duration) | Session data |
| **VIT** | Vitality | Recovery composite: sleep + HRV + resting HR | HealthKit |
| **END** | Endurance | Cardio minutes + step count vs goal | HealthKit |
| **CON** | Consistency | Streak days + workout frequency | Progress data |

Each stat: 0-100 scale, displayed in hexagon radar chart on profile.

**Stats unlock:**
- Cosmetics (titles, badge colors, avatar frames)
- Challenges (stat-gated raids)
- Skill tree features

---

## Implementation Phases

### Phase 1: Visual Celebrations - QUICK WIN
**Effort: Small | Impact: High**

New iOS components:
- `RankUpCelebrationView.swift` - Full-screen rank-up animation
- `PRCelebrationView.swift` - Compact PR fanfare overlay
- Enhanced XP bar level-up animation

Trigger when `WorkoutCreateResponse.rankChanged == true` or new PR detected.

**Files to modify:**
- `ios/.../Views/Log/LogView.swift` - Add celebration coordinator
- `ios/.../Components/` - New celebration views

---

### Phase 2: HealthKit Expansion
**Effort: Medium | Impact: High**

Add to `HealthKitManager.swift`:
```swift
// New data types
HKCategoryType.sleepAnalysis
HKQuantityType.heartRateVariabilitySDNN
HKQuantityType.restingHeartRate
HKQuantityType.bodyMass
HKObjectType.workoutType() // Auto-detect workouts
```

Backend: Add fields to `DailyActivity` model:
- `sleep_quality`, `sleep_deep_minutes`, `sleep_rem_minutes`
- `detected_workouts` count

**Files to modify:**
- `ios/.../Services/HealthKitManager.swift` - Add new data types + fetch functions
- `backend/app/models/activity.py` - Add sleep/recovery fields
- `backend/app/schemas/activity.py` - Update response schemas

---

### Phase 3: Stats System
**Effort: Large | Impact: High | Depends on: Phase 2**

#### Backend
New model: `backend/app/models/hunter_stats.py`
```python
class HunterStats(Base):
    user_id = Column(String, ForeignKey("users.id"), unique=True)
    power = Column(Integer, default=0)      # 0-100
    volume = Column(Integer, default=0)
    density = Column(Integer, default=0)
    vitality = Column(Integer, default=0)
    endurance = Column(Integer, default=0)
    consistency = Column(Integer, default=0)
    hunter_power_level = Column(Integer, default=0)  # Weighted avg
    last_calculated = Column(DateTime)
```

New service: `backend/app/services/stats_service.py`
- `calculate_power_stat()` - From PR/e1RM data
- `calculate_vitality_stat()` - From HealthKit recovery data
- `recalculate_all_stats()` - Full refresh

New endpoints: `backend/app/api/stats.py`
- `GET /api/stats` - Current stats
- `GET /api/stats/unlocks` - Cosmetics/features unlocked by stats

#### iOS
New components:
- `StatHexagonView.swift` - Radar chart visualization
- `StatBreakdownView.swift` - Detailed stat explanation

Modify:
- `ProfileView.swift` - Add hexagon to profile header
- `APITypes.swift` - Add stats response types

---

### Phase 4: Shop/Currency System
**Effort: Large | Impact: Medium | Depends on: Phase 3**

Currency: **Shadow Essence**
- Workouts: 10-50 essence (based on volume)
- PRs: 25 essence
- Streaks: 50-200 essence
- Achievements: 25-100 essence

#### Backend Models
```python
# user_currency table
UserCurrency: shadow_essence, total_earned, total_spent

# shop_items table
ShopItem: name, category, price, item_data (JSON), required_rank

# user_purchases table
UserPurchase: item_id, purchased_at, is_equipped
```

Shop categories:
- **Cosmetics**: Badge colors, avatar frames, profile backgrounds
- **Titles**: Custom titles ("The Iron", "Shadow Walker")
- **Consumables**: XP Boost (2x 24h), Streak Freeze, Quest Reroll

#### iOS Views
- `ShopView.swift` - Main shop
- `InventoryView.swift` - Equipped items
- Currency display in header

---

### Phase 5: Challenge/Raid System
**Effort: Large | Impact: High | Depends on: Phase 3**

#### Gate Raids (Multi-Day Challenges)
Example: "E-Rank Gate: Foundation"
- Day 1: Complete workout with 3+ exercises
- Day 2: Hit 100 total reps
- Day 3: Set any PR
- Reward: 500 XP + 100 Essence + "Gate Clearer" title

#### Boss Fights (Monthly PR Events)
"The Iron Golem" - Monthly bench challenge
- Goal: Beat current bench e1RM by 5+ lbs
- Bonus tier: 10+ lbs for extra rewards

#### Stat-Gating
- Power >= 60 for S-Rank gates
- Vitality >= 40 for recovery challenges
- Consistency >= 70 for endurance raids

#### Backend Models
```python
ChallengeDefinition: name, type, duration_days, requirements (JSON), objectives (JSON), rewards (JSON)
UserChallenge: challenge_id, started_at, progress (JSON), status
```

---

### Phase 6: Social Features
**Effort: Large | Impact: Medium**

- Weekly leaderboards (XP, volume, PRs, streak)
- Guild system (create/join, shared challenges)
- Friend 1v1 challenges

---

## Implementation Order

| Priority | Phase | Effort | Deliverable |
|----------|-------|--------|-------------|
| 1 | Celebrations | Small | Rank-up + PR animations |
| 2 | HealthKit | Medium | Sleep, HRV, auto-workout detection |
| 3 | Stats | Large | Hexagon display, stat calculation, unlocks |
| 4 | Shop | Large | Currency, cosmetics, consumables |
| 5 | Challenges | Large | Gate raids, boss fights |
| 6 | Social | Large | Leaderboards, guilds |

---

## Key Files Reference

**Backend:**
- `backend/app/models/progress.py` - Extend with stats relationship
- `backend/app/models/activity.py` - Add recovery fields
- `backend/app/services/xp_service.py` - Add currency awards
- New: `backend/app/models/hunter_stats.py`
- New: `backend/app/models/shop.py`
- New: `backend/app/models/challenge.py`
- New: `backend/app/services/stats_service.py`

**iOS:**
- `ios/.../Services/HealthKitManager.swift` - Expand data types
- `ios/.../Views/Profile/ProfileView.swift` - Add stat hexagon
- `ios/.../Utils/Colors.swift` - Reference for theming
- New: `ios/.../Components/StatHexagonView.swift`
- New: `ios/.../Components/RankUpCelebrationView.swift`
- New: `ios/.../Views/Shop/ShopView.swift`
- New: `ios/.../Views/Challenges/ChallengesView.swift`

---

## Verification

After each phase:
1. Run backend tests: `cd backend && pytest`
2. Regenerate Xcode project: `cd ios && xcodegen generate`
3. Build iOS app in Xcode, test on simulator
4. Manual testing of new features with real workout data
