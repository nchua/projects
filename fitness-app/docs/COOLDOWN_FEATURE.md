# Muscle Cooldown Tracking Feature

## Overview

This document describes the implementation of the muscle cooldown tracking feature, which displays muscle groups that are still cooling down on the iOS app's home screen based on recent workout history.

## Implementation Date
January 2026

## Architecture

### Backend Components

#### 1. Cooldown Schema (`backend/app/schemas/cooldown.py`)

Defines the data models for cooldown status:

```python
class AffectedExercise(BaseModel):
    name: str
    performed_at: str
    fatigue_contribution: float  # 0-100%

class MuscleCooldownStatus(BaseModel):
    muscle_group: str           # e.g., "Chest", "Quads"
    fantasy_name: str           # e.g., "Titan's Core", "Earth Pillars"
    cooldown_percent: float     # 0-100 (100 = fully ready)
    hours_remaining: float      # Hours until fully ready
    affected_exercises: List[AffectedExercise]

class CooldownResponse(BaseModel):
    muscles_cooling: List[MuscleCooldownStatus]
    generated_at: str
```

#### 2. Cooldown Service (`backend/app/services/cooldown_service.py`)

Core logic for calculating muscle fatigue:

**Science-Based Cooldown Times:**
| Muscle Group | Cooldown Hours |
|--------------|----------------|
| Chest, Hamstrings, Back | 72 hours |
| Quads, Glutes, Shoulders | 48 hours |
| Biceps, Triceps, Forearms, Calves, Core | 36 hours |

**Exercise-to-Muscle Mapping:**
- 100+ exercises mapped to primary and secondary muscle groups
- Compound exercises transfer fatigue to multiple muscles:
  - Primary muscles: 100% fatigue contribution
  - Secondary muscles: 50% fatigue contribution

**Example Mappings:**
```python
"bench press": {"primary": ["chest"], "secondary": ["triceps", "shoulders"]}
"squat": {"primary": ["quads", "glutes"], "secondary": ["hamstrings", "core"]}
"deadlift": {"primary": ["back", "hamstrings"], "secondary": ["glutes", "forearms"]}
```

#### 3. Analytics Endpoint (`backend/app/api/analytics.py`)

```
GET /analytics/cooldowns
Authorization: Bearer <token>

Response:
{
  "muscles_cooling": [...],
  "generated_at": "2026-01-05T10:30:00"
}
```

### iOS Components

#### 1. API Types (`Services/APITypes.swift`)

```swift
struct CooldownResponse: Codable {
    let musclesCooling: [MuscleCooldownStatus]
    let generatedAt: String
}

struct MuscleCooldownStatus: Codable, Identifiable {
    let muscleGroup: String
    let fantasyName: String
    let cooldownPercent: Double
    let hoursRemaining: Double
    let affectedExercises: [AffectedExercise]
}
```

#### 2. API Client (`Services/APIClient.swift`)

```swift
func getCooldownStatus() async throws -> CooldownResponse {
    return try await get("/analytics/cooldowns")
}
```

#### 3. Home View Model (`Views/Home/HomeViewModel.swift`)

Cooldown status is fetched in parallel with other home screen data:

```swift
async let cooldownTask = APIClient.shared.getCooldownStatus()
// ... other async tasks ...
cooldownStatus = cooldowns.musclesCooling
```

#### 4. Cooldown Card Component (`Components/CooldownCard.swift`)

Visual design following the "System Window" style:
- Lightning bolt icon with cyan glow
- Holographic gradient border
- Grid layout for muscle cells
- Fill-up animation showing cooldown progress
- Expandable to show affected exercises
- Fantasy-themed muscle names for gamification

#### 5. Home View Integration (`Views/Home/HomeView.swift`)

```swift
// Cooldown Status Card - Only show if there are muscles cooling down
if !viewModel.cooldownStatus.isEmpty {
    CooldownCard(cooldownData: viewModel.cooldownStatus)
        .padding(.horizontal)
}
```

## Design Decisions

### 1. Only Show When Relevant

The CooldownCard only appears when there are muscles cooling down. This keeps the home screen clean when the user hasn't worked out recently.

### 2. Fantasy Naming Convention

To align with the Solo Leveling theme, muscles have fantasy names:
- Chest → "Titan's Core"
- Quads → "Earth Pillars"
- Back → "Dragon's Spine"
- etc.

### 3. Compound Exercise Handling

Compound exercises (bench press, squat, deadlift) affect multiple muscle groups with weighted fatigue:
- Primary muscles get 100% fatigue contribution
- Secondary muscles get 50% fatigue contribution

This more accurately reflects real-world muscle cooldown patterns.

### 4. Science-Based Cooldown Times

Cooldown times are based on muscle size and typical recovery research:
- Large muscles need more cooldown time (72h)
- Small muscles cool down faster (36h)

## Lessons Learned

### 1. API Response Format Matters

When designing the API response, we included both raw data (`muscleGroup`) and display data (`fantasyName`). This allows the iOS app to use the appropriate name based on context without needing a local mapping table.

### 2. Conditional UI Rendering

Instead of always showing the CooldownCard with "No muscles cooling" text, we chose to hide it entirely when empty. This reduces visual clutter and makes the home screen more dynamic.

### 3. Parallel Data Fetching

Using Swift's `async let` for parallel fetching significantly improves home screen load time:

```swift
// Good: Parallel fetching
async let cooldownTask = APIClient.shared.getCooldownStatus()
async let workoutsTask = APIClient.shared.getWorkouts()

// Bad: Sequential fetching
let cooldowns = try await APIClient.shared.getCooldownStatus()
let workouts = try await APIClient.shared.getWorkouts()
```

### 4. Exercise Name Normalization

Exercise names from user input can vary ("Bench Press", "bench press", "Barbell Bench Press"). The cooldown service normalizes names to lowercase and checks for partial matches to handle variations.

### 5. Testing Challenges

Automated UI testing in iOS Simulator proved difficult due to:
- HealthKit permission dialogs blocking initial app launch
- Simulator touch input requiring specific tools (cliclick)
- Coordinate calculations for dynamic window positions

**Recommendation:** For future features, consider adding debug endpoints or test modes that can bypass permission dialogs.

## Files Changed

### Backend (3 new files)
- `backend/app/schemas/cooldown.py`
- `backend/app/services/cooldown_service.py`
- `backend/app/api/analytics.py` (modified - added cooldowns endpoint)

### iOS (5 files)
- `ios/FitnessApp/Services/APITypes.swift` (modified)
- `ios/FitnessApp/Services/APIClient.swift` (modified)
- `ios/FitnessApp/Views/Home/HomeViewModel.swift` (modified)
- `ios/FitnessApp/Views/Home/HomeView.swift` (modified)
- `ios/FitnessApp/Components/CooldownCard.swift` (new)

## Testing

### Manual Testing Steps

1. Log a workout with mapped exercises (Bench Press, Squat, Deadlift, etc.)
2. Navigate to Home screen
3. CooldownCard should appear showing muscles cooling down
4. Verify cooldown percentages increase over time (towards 100% ready)
5. After 72 hours, all muscles should show 100% ready (card hidden)

### API Testing

```bash
# Get cooldown status (requires auth token)
curl -H "Authorization: Bearer <token>" \
  https://backend-production-e316.up.railway.app/analytics/cooldowns
```

## Future Improvements

1. **Push Notifications:** Notify users when muscles are fully ready
2. **Workout Suggestions:** Recommend which muscle groups to train based on cooldown status
3. **Historical Cooldown Data:** Track cooldown patterns over time
4. **Custom Cooldown Times:** Allow users to adjust cooldown times based on their experience level
5. **Integration with Sleep/HRV:** Factor in sleep quality and HRV for more accurate cooldown estimates
6. **Dynamic Cooldown Calculation:** Make cooldown times adaptive based on multiple research-backed factors:

   **A. Muscle Group-Specific Recovery**
   - Different muscles have different baseline recovery needs based on fiber composition
   - Chest/Pecs: 65% fast-twitch fibers → longer recovery (72h baseline)
   - Lower body: generally needs longer recovery than upper body
   - Multi-joint movements need longer recovery than single-joint exercises
   - Sources: [PMC Systematic Review 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11057610/)

   **B. Age-Based Recovery Benchmarks**
   - Research shows recovery time increases significantly with age
   - Suggested modifiers:
     - Under 30: 1.0x baseline
     - 30-40: 1.15x baseline
     - 40-50: 1.3x baseline
     - 50+: 1.5x baseline
   - Sources: [Age-Related Recovery Research](https://pmc.ncbi.nlm.nih.gov/articles/PMC10854791/)

   **C. Workout Intensity Factors**
   - Number of sets performed for that muscle group (higher volume = longer cooldown)
   - Weight lifted relative to user's max (e.g., 90% of 1RM = +20% cooldown)
   - Training to failure adds 24-48h to recovery time per research
   - RPE/RIR if logged (RPE 10 = +50% cooldown time)

   **D. Training Frequency Adaptation (Detraining Effect)**
   - Less frequent training of a muscle = longer perceived fatigue
   - Regular training = muscles adapt and recover faster
   - Track historical frequency per muscle group
   - First workout after 2+ weeks off = +25% cooldown time
