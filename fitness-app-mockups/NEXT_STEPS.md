# ARISE Fitness App - Next Steps

## Mockups Complete (12 screens)

| File | Description |
|------|-------------|
| `01-login.html` | ARISE welcome - "You have been chosen" |
| `02-awakening.html` | Hunter registration with profile data |
| `03-dashboard.html` | Hunter status + weekly quest preview |
| `04-quest.html` | Weekly quest with Big 3, time, accessories |
| `05-history.html` | E1RM cards, trends chart, session log |
| `06-completion.html` | Victory rewards screen |
| `07-penalty.html` | Failed quest warning (glitch aesthetic) |
| `08-log-workout.html` | Set-by-set workout logging |
| `index.html` | Status header design options (A-D) with rank/class selectors |
| `onboarding.html` | 7-step class assignment flow |
| `class-change.html` | Reawakening system (class change with penalties) |
| `specializations.html` | Subclass progression UI (profile, detection, unlock) |

---

## Session Log

### January 10, 2026 - Subclass System & Typography Fixes

**Design Changes:**
- Redesigned class progression: instead of paying to change class, users now earn **subclasses** through training patterns
- 14 subclasses (2 per base class) with unique unlock requirements and XP bonuses
- Subclass mechanics: one active at a time, can switch between unlocked, hidden until 50% progress

**Class Change Updates:**
- Cost increased: 500 XP → 5,000 XP
- New penalty: lose ALL unlocked subclasses
- Cooldown increased: 30 days → 90 days

**UI Work:**
- Created `specializations.html` mockup with 3 views:
  - Profile view (active/unlocked/in-progress subclasses)
  - Detection notification ("[Specialization detected]")
  - Unlock celebration screen with particle animations
- Removed all-caps typography across all mockups (changed `text-transform: uppercase` to sentence case)

**Files Modified:**
- `specializations.html` (new)
- `index.html` (typography)
- `onboarding.html` (typography)
- `class-change.html` (typography)
- `docs/CLASS_SYSTEM.md` (subclass system documentation)

**Commits:**
- `d7fb823` - Add subclass system and specializations UI mockups
- `06db185` - Add subclass system documentation to CLASS_SYSTEM.md

---

## Decisions Needed Before Building

### 1. Tech Stack
| Option | Pros | Cons |
|--------|------|------|
| **React + TypeScript** | Scalable, follows Solo Leveling plan, component reuse | Bigger rebuild effort |
| **Vanilla JS** | Faster MVP, keeps existing dashboard work | Harder to maintain long-term |
| **Hybrid** | Start vanilla, migrate to React later | May duplicate work |

### 2. Backend / Data Storage
| Option | Pros | Cons |
|--------|------|------|
| **Supabase** | Cloud sync, auth, real-time, free tier | Requires account, internet |
| **Local JSON/SQLite** | Offline-first, simple, works now | No sync across devices |
| **Firebase** | Good free tier, easy auth | Google ecosystem lock-in |

### 3. Quest Generation
| Option | Pros | Cons |
|--------|------|------|
| **Claude API** | Dynamic, personalized quests | API costs, complexity |
| **Pre-defined templates** | Simple, predictable | Less variety |
| **Manual** | Full control | More user effort |

---

## Implementation Phases

### Phase 1: Core App
- [ ] Set up project structure (React or vanilla)
- [ ] Build design system (CSS variables, fonts, components)
- [ ] Implement login/awakening flow
- [ ] Build dashboard with real data integration
- [ ] Create bottom navigation

### Phase 2: Quest System
- [ ] Weekly quest data model
- [ ] Quest generation logic (based on goals)
- [ ] Progress tracking (sets completed, time logged, accessories)
- [ ] Connect workout logging to quest progress
- [ ] Quest completion/failure detection

### Phase 3: Workout Logging
- [ ] Exercise input with autocomplete
- [ ] Set-by-set logging (weight, reps, warmup flag)
- [ ] Session timer
- [ ] Rest timer between sets
- [ ] Notes per exercise
- [ ] Previous workout reference

### Phase 4: Analytics
- [ ] E1RM calculations (Epley formula)
- [ ] Progress charts (Chart.js or similar)
- [ ] PR detection and badges
- [ ] Percentile comparisons
- [ ] Volume/tonnage tracking

### Phase 5: Gamification
- [ ] XP and leveling system
- [ ] Rank progression (E → D → C → B → A → S)
- [ ] Stat points allocation
- [ ] Titles and achievements
- [ ] Streak tracking
- [ ] Loot boxes (optional)

### Phase 6: Polish
- [ ] Animations (Framer Motion or CSS)
- [ ] Sound effects (optional)
- [ ] PWA setup (offline, installable)
- [ ] Push notifications for quest deadlines

---

## Data to Migrate

### From `/Users/nickchua/Desktop/AI/Fitness/`
- `workout_log.json` - 12 workout sessions (Dec 12-31, 2025)
- `dashboard/dashboard_data.json` - Profile, lift stats, ratios

### User Profile
```json
{
  "name": "Nick",
  "age": 29,
  "height_in": 69,
  "bodyweight_lb": 166,
  "training_frequency": "3x/week"
}
```

### Current E1RMs
- Squat: 270 lb (1.63x BW) - Late Intermediate
- Bench: 185 lb (1.11x BW) - Early Intermediate
- Deadlift: 239 lb (1.44x BW) - Early Intermediate
- Row: 170 lb (1.02x BW) - High Intermediate

---

## Goals (Current Focus)

1. **Big Three Lifts** - Squat, Bench, Deadlift (weekly set targets)
2. **Total Exercise Time** - Weekly minutes goal
3. **Accessories** - Biceps, Triceps, Shoulders, Back, Core, Calves

Future: Allow custom goal configuration

---

## Design System Reference

### Colors
```css
--system-primary: #00D4FF;      /* The System Blue */
--void-black: #0A0A0F;          /* Background */
--rank-e: #808080;              /* Gray */
--rank-s: #FF4444;              /* Crimson */
--success-green: #33FF88;
--gold: #FFD700;
--warning-red: #FF3333;
```

### Fonts
- **Display**: Orbitron (titles, numbers)
- **Headers**: Rajdhani (section headers)
- **Body**: Inter (readable text)
- **Mono**: JetBrains Mono (system messages, data)

### Fantasy Exercise Names
| Exercise | Fantasy Name |
|----------|--------------|
| Squat | "Earth Shaker" |
| Bench Press | "Titan's Press" |
| Deadlift | "Grave Riser" |
| Barbell Row | "Serpent's Pull" |
| OHP | "Sky Piercer" |
| Barbell Curl | "Iron Coil" |
| Tricep Pulldown | "Shadow Strike" |

---

## Open Questions

1. React rebuild or enhance existing vanilla JS dashboard?
2. Cloud sync (Supabase) or keep local-first?
3. Which phase to start with?
4. AI quest generation now or later?

---

## Reference Documents

- `/Users/nickchua/Desktop/AI/SOLO_LEVELING_WORKOUT_APP_PLAN.md` - Original detailed spec
- `/Users/nickchua/Desktop/AI/Fitness/CLAUDE.md` - Current fitness app conventions
- `/Users/nickchua/Desktop/AI/fitness-app-mockups/` - All mockup files
