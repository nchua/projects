# Class System Design

## Overview

This document summarizes the class selection and class change system designed for the fitness app. The system is inspired by Solo Leveling's aesthetic and gamification mechanics.

**Mockups Location**: `/Users/nickchua/Desktop/AI/fitness-app-mockups/`
- `index.html` - Status header mockups (Option D: Class Card chosen)
- `onboarding.html` - Class assignment flow during signup
- `class-change.html` - Reawakening system for changing class

---

## Classes

### Rarity Tiers

| Rarity | Distribution | Bonus XP | Color |
|--------|-------------|----------|-------|
| Common | ~40% | 0 | Gray `#808080` |
| Uncommon | ~35% | 0 | Green `#4A9B4A` |
| Rare | ~20% | +25 | Blue `#4A7BB5` |
| Legendary | <5% | +50 | Purple `#9B4A9B` |

### Class Definitions

| Class | Rarity | Icon | Focus | Assignment Triggers |
|-------|--------|------|-------|---------------------|
| **Guardian** | Common | 🛡️ | Balanced, general fitness | General health goal, mixed background |
| **Warrior** | Uncommon | ⚔️ | Strength, compound lifts | Strength goal + heavy compound style |
| **Titan** | Uncommon | 💎 | Hypertrophy, aesthetics | Build muscle goal + bodybuilding style |
| **Ranger** | Uncommon | 🏹 | Endurance, cardio | Endurance goal + cardio style + track/swimming |
| **Monk** | Rare | ☯️ | Calisthenics, mobility | Calisthenics style + mobility goal + martial arts/yoga |
| **Berserker** | Rare | 🔥 | High intensity, CrossFit | CrossFit background + functional style + multiple goals |
| **Shadow** | Legendary | 👁️ | Contradictory path | Combat sports + calisthenics + strength + fat loss (hidden trigger) |

### Legendary Class Rules
- Cannot be manually selected during class change
- Only assigned during onboarding via specific hidden combinations
- Possible future mechanic: every X signups increases chance of rare class

---

## Onboarding Flow (Class Assignment)

### Steps

1. **Welcome** - Name input, "[SYSTEM INITIALIZING]" theming
2. **Training Experience** - Single select:
   - New to Training (<6 months)
   - Intermediate (6mo - 2yr)
   - Advanced (2-5yr)
   - Elite (5+ yr, competitive)
3. **Athletic Background** - Multi-select chips by category:
   - Combat: Boxing, MMA, Wrestling, BJJ
   - Team: Basketball, Football, Soccer, Volleyball, Hockey, Baseball
   - Individual: Swimming, Track, Tennis, Cycling, Weightlifting, Gymnastics
   - Other: Yoga, Dance, Climbing, CrossFit, None
4. **Training Style** - Single select:
   - Heavy Compound Lifts
   - Bodybuilding / Isolation
   - Functional / Athletic
   - Calisthenics / Bodyweight
   - Cardio / Endurance
5. **Goals** - Multi-select:
   - Get Stronger
   - Build Muscle
   - Lose Fat
   - Improve Endurance
   - Increase Mobility
   - Athletic Performance
   - General Health
6. **Processing** - Animated scan with checklist
7. **Class Reveal** - Dramatic card reveal with rarity badge

### Class Assignment Logic (To Implement)

```python
def assign_class(profile):
    # Legendary triggers (hidden, check first)
    if has_combat_sports(profile) and profile.style == "calisthenics" \
       and "strength" in profile.goals and "fat_loss" in profile.goals:
        return "shadow"  # Legendary
    
    # Rare classes
    if profile.style == "calisthenics" and "mobility" in profile.goals:
        return "monk"
    if "crossfit" in profile.sports or (profile.style == "functional" and len(profile.goals) >= 4):
        return "berserker"
    
    # Uncommon classes
    if profile.style == "compound" and "strength" in profile.goals:
        return "warrior"
    if profile.style == "bodybuilding" and "muscle" in profile.goals:
        return "titan"
    if profile.style == "cardio" and "endurance" in profile.goals:
        return "ranger"
    
    # Default
    return "guardian"  # Common
```

---

## Subclass System (Specializations)

### Overview

Instead of easily changing classes, users unlock **subclasses** through their training patterns. This rewards consistent effort and creates meaningful progression.

### Mechanics

| Setting | Value |
|---------|-------|
| **Active Subclass** | One at a time |
| **Switching** | Free between unlocked subclasses |
| **Unlock Visibility** | Hidden until ~50% progress |
| **Benefits** | XP multipliers, unique quests, cosmetic badges |

### Subclass Definitions

| Base Class | Subclass | Unlock Requirement | XP Bonus | Unique Perk |
|------------|----------|-------------------|----------|-------------|
| **Guardian** | Sentinel | Log 50 workouts | +10% all XP | "Consistency" quest line |
| **Guardian** | Protector | 30 days streak | +15% streak XP | Extended streak protection |
| **Warrior** | Powerlifter | 100 sets at RPE 8+ | +20% compound XP | "Max Out" weekly quest |
| **Warrior** | Strongman | Train 8+ different compounds | +15% variety XP | Equipment mastery badges |
| **Titan** | Sculptor | 200 isolation exercise sets | +20% isolation XP | "Pump" bonus quests |
| **Titan** | Mass Monster | 500,000 lbs total volume | +15% volume XP | Volume milestone badges |
| **Ranger** | Marathoner | 50 cardio sessions 30+ min | +20% endurance XP | Long session bonuses |
| **Ranger** | Sprinter | 30 HIIT sessions | +20% HIIT XP | "Burst" daily quests |
| **Monk** | Ascetic | 100 bodyweight-only workouts | +25% calisthenics XP | Movement mastery tree |
| **Monk** | Sage | 50 mobility/yoga sessions | +20% recovery XP | "Balance" quest line |
| **Berserker** | Warlord | Complete 25 workouts under 45 min | +20% efficiency XP | Speed challenge quests |
| **Berserker** | Destroyer | Hit 50 PRs | +25% PR XP | PR hunt weekly quest |
| **Shadow** | Phantom | ??? (hidden) | +30% all XP | ??? |
| **Shadow** | Monarch | ??? (hidden) | +35% all XP | ??? |

### Unlock Flow

1. **Hidden Phase** (0-49% progress)
   - User trains normally
   - No indication of subclass requirements
   - Progress tracked silently in background

2. **Reveal Phase** (50%+ progress)
   - System notification: "[SPECIALIZATION DETECTED]"
   - Shows subclass name, icon, and remaining requirements
   - Progress bar appears in Profile

3. **Unlock Phase** (100% complete)
   - Dramatic reveal animation
   - Subclass badge awarded
   - Option to activate immediately or stay with current

### Subclass UI Elements

**Profile Section:**
```
┌─────────────────────────────────────┐
│  SPECIALIZATIONS                    │
│                                     │
│  [✓] Powerlifter (Active)           │
│      +20% compound XP               │
│                                     │
│  [✓] Strongman (Unlocked)           │
│      Tap to activate                │
│                                     │
│  [░░░░░░░░░░] 67%                   │
│  Warlord - 8 more fast workouts     │
└─────────────────────────────────────┘
```

**Notification Examples:**
- "[SYSTEM] Specialization path detected: Powerlifter (52% complete)"
- "[SYSTEM] Powerlifter unlocked! +20% XP on compound lifts activated."

---

## Class Change (Reawakening)

### Mechanics

Class changes are intentionally costly to make your initial class meaningful.

| Setting | Value |
|---------|-------|
| **Cost** | 5,000 XP |
| **Penalty** | Lose ALL unlocked subclasses |
| **Cooldown** | 90 days |
| **Legendary Access** | Locked (cannot select manually) |

### Screens

1. **Main Screen** (when available)
   - Current class card with stats
   - Warning: "You will lose X unlocked subclasses"
   - Cost banner (5,000 XP) + user's current XP
   - Class selection list (current grayed, legendary locked)
   - Confirm button → opens modal

2. **Confirmation Modal**
   - From → To class visualization
   - XP cost deduction shown
   - List of subclasses that will be lost
   - 90-day cooldown warning
   - "I understand" checkbox required
   - Cancel / Confirm buttons

3. **Cooldown Screen**
   - Red "X days remaining" notice
   - All classes grayed out
   - Button disabled with countdown

4. **Success Screen**
   - Animated class transformation
   - New class card reveal
   - "Start fresh" messaging
   - Continue button

---

## Status Header (Class Card Design)

### Chosen Design: Option D - Class Card

Removed the grey "Hunter Class" header bar. Current layout:

```
┌─────────────────────────────────────┐
│  ┌──────┐                           │
│  │  E   │  Nick                     │
│  │ rank │  [Warrior] class badge    │
│  └──────┘  10 Level    🔥1 Streak   │
│                                     │
│  [========-----] XP Progress        │
│  3,436 / 3,648                      │
│  Saturday, January 10  212 XP to go │
└─────────────────────────────────────┘
```

### Key Changes from Original
- Replaced "H" initial placeholder with rank emblem (E, D, C, B, A, S)
- Name pulled from user profile (not hardcoded "Hunter")
- Class badge shows assigned class (e.g., "Warrior")
- Rank-colored border on card

---

## Color Scheme

```css
/* Backgrounds */
--void-black: #0A0A0F;
--void-dark: #12121A;
--void-medium: #1A1A24;
--void-light: #252530;

/* Accent */
--system-primary: #00D4FF;
--system-dim: #00A8CC;

/* Rarity */
--rarity-common: #808080;
--rarity-uncommon: #4A9B4A;
--rarity-rare: #4A7BB5;
--rarity-legendary: #9B4A9B;

/* Rank Colors */
--rank-e: #808080;
--rank-d: #4A9B4A;
--rank-c: #4A7BB5;
--rank-b: #9B4A9B;
--rank-a: #FFD700;
--rank-s: #FF4444;
```

---

## Implementation TODO

### Backend - Class System
- [ ] Add `user_class` field to user profile model
- [ ] Add `class_changed_at` timestamp for cooldown tracking
- [ ] Create `/api/class/change` endpoint with XP deduction (5000 XP), cooldown (90 days), and subclass reset
- [ ] Implement class assignment algorithm based on onboarding answers
- [ ] Store onboarding responses for class calculation

### Backend - Subclass System
- [ ] Create `UserSubclass` model (user_id, subclass_id, unlocked_at, is_active)
- [ ] Create `SubclassProgress` model (user_id, subclass_id, current_value, target_value)
- [ ] Add subclass progress tracking to workout save logic
- [ ] Create `/api/subclass/progress` endpoint (returns visible subclasses at 50%+)
- [ ] Create `/api/subclass/activate` endpoint (switch active subclass)
- [ ] Implement XP multiplier calculation based on active subclass
- [ ] Add subclass unlock event notifications

### iOS App - Class System
- [ ] Update `HunterStatusHeader` to show class badge instead of rank title
- [ ] Create `ClassChangeView` screen accessible from Profile
- [ ] Add onboarding flow after registration
- [ ] Store selected goals/sports/style in user profile

### iOS App - Subclass System
- [ ] Create `SpecializationsView` in Profile section
- [ ] Show unlocked subclasses with activate/deactivate toggle
- [ ] Show in-progress subclasses (50%+) with progress bars
- [ ] Create subclass unlock celebration animation
- [ ] Add "[SPECIALIZATION DETECTED]" notification banner
- [ ] Display active subclass XP bonus on workout completion

### Database Schema Addition
```sql
-- Class system
ALTER TABLE user_profiles ADD COLUMN class VARCHAR(20) DEFAULT 'guardian';
ALTER TABLE user_profiles ADD COLUMN class_changed_at TIMESTAMP;
ALTER TABLE user_profiles ADD COLUMN onboarding_data JSONB;

-- Subclass system
CREATE TABLE subclasses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    base_class VARCHAR(20) NOT NULL,
    unlock_type VARCHAR(50) NOT NULL,  -- 'sets_at_rpe', 'workout_count', 'volume', etc.
    unlock_target INTEGER NOT NULL,
    xp_bonus_percent INTEGER NOT NULL,
    xp_bonus_category VARCHAR(50),  -- 'compound', 'isolation', 'all', etc.
    unique_perk TEXT
);

CREATE TABLE user_subclasses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    subclass_id INTEGER REFERENCES subclasses(id),
    unlocked_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT FALSE,
    UNIQUE(user_id, subclass_id)
);

CREATE TABLE subclass_progress (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    subclass_id INTEGER REFERENCES subclasses(id),
    current_value INTEGER DEFAULT 0,
    revealed_at TIMESTAMP,  -- NULL until 50% reached
    UNIQUE(user_id, subclass_id)
);
```

---

## Files Created

```
/Users/nickchua/Desktop/AI/fitness-app-mockups/
├── index.html            # Status header mockups with class selector
├── onboarding.html       # 7-step class assignment flow
├── class-change.html     # Reawakening system (3 states)
└── specializations.html  # Subclass progression UI (profile, detection, unlock)
```

---

## Notes for Next Session

1. **Rare class lottery idea**: Every X signups could increase chance of legendary class
2. **Class-specific perks**: Could add XP multipliers or quest bonuses per class
3. **Class leaderboards**: Show top users per class
4. **Class-specific quests**: Tailored daily challenges based on class focus
