# Design Refresh: Quest/Home UI -- "ARISE 2.0"

> **Process:** Every implementation phase below requires an HTML mockup (`ios/mockups/<component>.html`) approved before writing Swift code. Each phase lists its required mockup.

## Current State

### What Works Well

1. **Strong thematic identity** -- Solo Leveling aesthetic is genuinely unique in the fitness app space. Void-black backgrounds, cyan accents, rank system, fantasy exercise names create distinctive brand.
2. **Comprehensive color system** -- `Colors.swift` has thorough palette with semantic naming: rank colors, exercise colors, glow variants, gradients.
3. **Custom typography stack** -- Orbitron for display numbers, Rajdhani for headers, JetBrains Mono for stats. Thoughtful hierarchy.
4. **Animation infrastructure** -- Shimmer, pulse glow, fade-in, slide-in modifiers. `AriseProgressBar` with shimmer is polished.
5. **Feature richness** -- Missions, daily quests, power levels, cooldowns, weekly reports, achievements -- lots of real content.

### What Feels Dated and Why

**Problem 1: Two design systems coexisting**

Unresolved identity crisis between:
- **ARISE system** (legacy): Sharp `cornerRadius: 4`, monospace tags like `[ WEEKLY QUEST ]`, bracket notation, `systemPanelStyle()` with 4px corners. Feels very 2020 "cyberpunk terminal."
- **Edge Flow system** (newer): `cornerRadius: 14-16`, capsule pills, softer backgrounds, `edgeFlowCard()`. Feels more modern iOS 17/18-era.

The home screen mixes both. `MissionCard` uses Edge Flow (16px corners). Legacy components (`LastQuestCard`, `WeeklyQuestCard`, `CooldownCard`) still use ARISE (4px corners, bracket text). **This inconsistency is the single biggest contributor to the "outdated" feeling.**

**Problem 2: Information overload (9 sections)**

Home screen has up to 9 sections stacked vertically:
1. HunterStatusHeader
2. StatsScrollSection
3. QuickActionsRow
4. MissionCard
5. DailyQuestsSection
6. PowerLevelsSection
7. WeeklyReportCard
8. RecoveryStatusSection
9. Latest Achievement

Takes 3-4 screen-heights to see everything. Competitors (Hevy, Strong) show 2-3 sections above the fold. Lower sections (Recovery, Achievements) likely have extremely low engagement.

**Problem 3: Generic stat cards**

`EdgeFlowStatCard` renders "2 / Workouts", "14.5K / Volume" in identical dark rectangles. Raw numbers with no context, no comparison to last week, no visual metaphor.

**Problem 4: "Start Workout" CTA is buried**

Most important action sits in position 3 (below header and stats). Two capsule pills of equal visual weight -- "Start Workout" and "Scan" -- compete for attention. Modern fitness apps use a floating action button or sticky CTA.

**Problem 5: Emoji overuse**

Unicode emoji everywhere: weight lifter, flexed bicep, target, stopwatch, crossed swords, fire, trophy. Emojis render differently across iOS versions, look "undesigned," and break the premium feel.

**Problem 6: MissionCard has 6 visual states**

Loading, error, empty, ready, active, mid-week -- each renders a completely different card shape with 7 callback closures. Inconsistent week-to-week experience.

**Problem 7: No breathing room**

`VStack(spacing: 16)` creates uniform gaps. No spatial hierarchy. No "hero" moment.

**Problem 8: Grid background is distracting**

`VoidBackground(showGrid: true)` renders 50px grid. Fights the softer Edge Flow cards. Modern dark apps (Apple TV, Spotify, Arc) use subtle gradient blurs, not grids.

---

## Proposed Design: "ARISE 2.0 -- Minimal Void"

### Philosophy
Keep Solo Leveling identity but evolve from "2020 cyberpunk terminal" to "2026 premium dark UI." Goal: if someone sees the app on the subway, it looks **premium** and **intentional**, not like a dev's side project.

**Reference mood:** Apple Activity app's clarity meets Arc browser's dark mode meets Solo Leveling accents.

**Core principles:**
- Commit to Edge Flow, sunset ARISE sharp corners entirely
- Reduce visible sections from 9 to 5-6
- One clear "hero" zone above the fold
- Replace emojis with SF Symbols
- Depth through blur layers, not grid patterns
- Motion used sparingly but meaningfully

---

### New Home Screen Layout (6 sections, down from 9)

#### 1. Background: Ambient Gradient (replaces grid)

Remove `GridPattern` entirely. Replace with:
- Base: solid `#050508`
- Top ambient: radial gradient from `systemPrimary` at 2% opacity, centered behind header
- Optional: subtle noise texture at 1-2% opacity for depth

#### 2. Hunter Header: Compact (90px, down from ~140px)

```
[Avatar 40px] [Name bold]         [Level badge] [Streak]
              [Rank title dimmed] [====XP bar inline====]
```

Changes:
- Shrink avatar to 40px
- Replace weight-lifter emoji with SF Symbol (`figure.strengthtraining.traditional`) or user photo
- XP bar inline with top row (saves ~20px)
- Remove radial glow overlay (too subtle to notice)

#### 3. Dashboard Card (NEW -- replaces stats scroll + quick actions)

```
+--------------------------------------------------+
|  This Week              2 of 4 workouts           |
|  [===========----------]  50%                     |
|                                                    |
|  24.5K vol   |   135 min   |   +2 PRs             |
|                                                    |
|  [=== Start Workout (full width, gradient) ===]   |
+--------------------------------------------------+
```

- Most important stat (weekly count) front and center
- Supporting stats below
- CTA right there -- no separate section needed
- "Scan" moves to Log tab or becomes secondary icon on CTA
- Card style: `cornerRadius: 20`, glass-morphic background, thin 1px border at 5% opacity

#### 4. Mission Card (Simplified -- 2 visual states, down from 6)

- **Empty/Setup:** Clean card with target icon + "Set Your First Goal" CTA. Single button.
- **Active:** Compact progress card with goal name, large centered progress ring, days remaining, "View Details" link.
- All sub-states (offered, mid-week, etc.) use same card shape with different content
- "Accept Mission" flow moves to a sheet (doesn't clutter the card)
- `cornerRadius: 20`. No left-accent bar (ARISE holdover). Use subtle top-border gradient instead.

#### 5. Power Levels Card (Combined -- replaces 3 separate scroll cards)

```
+--------------------------------------------------+
|  Power Levels                          Details >  |
|                                                    |
|   SQUAT        BENCH        DEADLIFT              |
|   [minibar]    [minibar]    [minibar]             |
|    285         225           365                   |
|   +3.2%       -1.1%        +5.4%                  |
+--------------------------------------------------+
```

- Replace emojis with color-coded mini progress bars
- Trend direction with arrows and percentages
- Single card instead of three floating ones
- SF Symbols for trend arrows (`arrow.up.right`)

#### 6. Insights Scroll (Horizontal -- replaces 3 vertical sections)

Combines Weekly Report + Recovery + Latest PR into one horizontal scroll:
- **Weekly Report card** (keep as-is, well-designed)
- **Recovery summary** ("Chest -- 8h remaining") with tap-to-expand
- **Latest PR card** (if any)

Turns 3 vertical sections into 1 horizontal row, reclaiming ~400px scroll height.

#### 7. Floating Action Button

Persistent FAB above tab bar, always visible:
- 56px circle, gradient fill (systemPrimary to darker cyan)
- Subtle shadow, `bolt.fill` icon in white
- The Dashboard card CTA can be softer since FAB is always available

---

### Global Style Changes

**Cards:**
- Primary cards: `cornerRadius: 20`
- Compact/inline cards: `cornerRadius: 12`
- Background: `Color.bgCard` (`#0f1018`)
- Border: `Color.white.opacity(0.04)`, 1px
- No left accent bars -- use top-border gradients sparingly
- Shadow: `Color.systemPrimary.opacity(0.03)`, radius 20, y: 8

**Emoji -> SF Symbol Mapping:**
| Emoji | SF Symbol |
|-------|-----------|
| Weight lifter `\u{1F3CB}` | `figure.strengthtraining.traditional` |
| Flexed bicep `\u{1F4AA}` | `dumbbell.fill` |
| Stopwatch `\u{23F1}` | `timer` |
| Trophy `\u{1F3C6}` | `trophy.fill` |
| Target `\u{1F3AF}` | `target` |
| Fire `\u{1F525}` | `flame.fill` |
| Crossed swords `\u{2694}` | `figure.fencing` |
| Lightning bolt `\u{26A1}` | `bolt.fill` |
| Chart `\u{1F4C8}` | `chart.line.uptrend.xyaxis` |
| Green check `\u{2705}` | `checkmark.circle.fill` |

---

## Interaction Details

### Animations
1. **Hero stat count-up** -- Weekly workout count and volume count from 0 to current over 0.6s with easing
2. **Mission progress ring** -- `withAnimation(.spring)` fill from 0 to current over 0.8s
3. **Staggered card reveals** -- `fadeIn` at 0.3s duration, 0.05s stagger per card (currently 0.1s feels slow)
4. **PR celebration** -- One-time gold shimmer on Achievement card at first appearance
5. **Haptic feedback** -- Medium impact on quest claims/mission accepts, light impact on card taps

### Transitions
1. **Pull-to-refresh** -- Custom cyan-tinted spinner matching theme (not default white)
2. **Sheet presentations** -- `.presentationDetents([.medium, .large])` with drag indicator
3. **Card tap** -- Subtle `scaleEffect(0.98)` for 0.1s before sheet appears

### Scroll Behavior
1. **Sticky header** -- Blur-transition into compact bar (name + level only) as user scrolls. Animate height from ~100px to ~50px using `GeometryReader`.
2. **Section snap** -- Insights horizontal scroll uses `.scrollTargetBehavior(.viewAligned)` for iOS 17+

---

## Onboarding: "The Awakening" (3 screens)

### Screen 1: "The System Has Awakened"
- Full-screen dark void with pulsing cyan glow center
- Animated text: "You have been chosen."
- Subtitle: "The Solo Leveling System will track your training and measure your strength."
- Button: "Begin Awakening" (full-width gradient)

### Screen 2: "Set Your Class"
- Two quick questions:
  - Training focus: Strength / Hypertrophy / General Fitness (three tappable cards)
  - Training frequency: 2-3x / 3-4x / 5-6x per week (pill selector)
- Sets `workoutsGoal` and primes coaching system

### Screen 3: "Your First Quest"
- Show E-Rank assignment ("Awakened") with brief animation
- Preview first daily quest
- Button: "Start Your First Workout" -> goes to Log tab

Implementation: One-time flow via `UserDefaults` flag (`hasCompletedOnboarding`). Full-screen covers with VoidBackground and cross-dissolve transitions.

---

## Implementation Sequencing

### Phase 1: Foundation (card system + background)
- `[MOCKUP]` **Mockup:** `ios/mockups/card-system-v2.html` -- show new card radii, backgrounds, borders side-by-side with old
- Update `EdgeFlowStyles.swift` to new card spec (20px radius)
- Replace `VoidBackground` grid with ambient gradient
- Update `Colors.swift` for any new tokens

### Phase 2: Header + Dashboard
- `[MOCKUP]` **Mockup:** `ios/mockups/dashboard-card.html` -- compact header + combined stats/CTA card
- Refactor `HunterStatusHeader` to compact layout
- Create new `DashboardCard` combining stats + CTA
- Remove `StatsScrollSection` and `QuickActionsRow`

### Phase 3: Mission card simplification
- `[MOCKUP]` **Mockup:** `ios/mockups/mission-card-v2.html` -- show both states (empty + active)
- Reduce `MissionCard` to 2 visual states
- Unify card shapes
- Move "Accept Mission" to sheet

### Phase 4: Power Levels + Insights
- `[MOCKUP]` **Mockup:** `ios/mockups/power-levels-insights.html` -- combined card + horizontal scroll
- Create combined `PowerLevelsCard`
- Create `InsightsScrollSection` (horizontal scroll combining Weekly Report, Recovery, Achievement)

### Phase 5: Polish
- `[MOCKUP]` **Mockup:** `ios/mockups/fab-and-symbols.html` -- FAB placement + SF Symbol replacements
- Replace all emojis with SF Symbols
- Add count-up animations
- Add haptic feedback
- Implement floating action button

### Phase 6: Onboarding
- `[MOCKUP]` **Mockup:** `ios/mockups/onboarding.html` -- all 3 screens
- Build 3-screen "Awakening" flow

---

## Files to Modify

| File | Changes |
|------|---------|
| `ios/FitnessApp/Views/Home/HomeView.swift` | Restructure layout from 9 to 6 sections |
| `ios/FitnessApp/Components/EdgeFlowStyles.swift` | Unify card system to 20px radius |
| `ios/FitnessApp/Components/MissionCard.swift` | Simplify from 6 to 2 visual states |
| `ios/FitnessApp/Components/VoidBackground.swift` | Replace grid with ambient gradient |
| `ios/FitnessApp/Utils/Colors.swift` | Add new tokens (glass borders, FAB gradient) |
| `ios/FitnessApp/Components/DailyQuestsCard.swift` | Collapse to summary pill |
| New: `ios/FitnessApp/Components/DashboardCard.swift` | Combined stats + CTA card |
| New: `ios/FitnessApp/Components/PowerLevelsCard.swift` | Combined 3-column card |
| New: `ios/FitnessApp/Components/InsightsScrollSection.swift` | Horizontal scroll |
| New: `ios/FitnessApp/Components/FloatingActionButton.swift` | Persistent FAB |
| New: `ios/FitnessApp/Views/Onboarding/OnboardingView.swift` | 3-screen awakening |
