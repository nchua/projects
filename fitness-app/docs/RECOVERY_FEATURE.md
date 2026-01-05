# Muscle Recovery Tracking Feature

## Overview

This document describes the implementation of the muscle recovery tracking feature, which displays fatigued muscle groups on the iOS app's home screen based on recent workout history.

## Implementation Date
January 2026

## Architecture

### Backend Components

#### 1. Recovery Schema (`backend/app/schemas/recovery.py`)

Defines the data models for recovery status:

```python
class AffectedExercise(BaseModel):
    name: str
    performed_at: str
    fatigue_contribution: float  # 0-100%

class MuscleRecoveryStatus(BaseModel):
    muscle_group: str           # e.g., "Chest", "Quads"
    fantasy_name: str           # e.g., "Titan's Core", "Earth Pillars"
    recovery_percent: float     # 0-100 (100 = fully recovered)
    hours_remaining: float      # Hours until full recovery
    affected_exercises: List[AffectedExercise]

class RecoveryResponse(BaseModel):
    fatigued_muscles: List[MuscleRecoveryStatus]
    last_workout_at: Optional[str]
```

#### 2. Recovery Service (`backend/app/services/recovery_service.py`)

Core logic for calculating muscle fatigue:

**Science-Based Recovery Times:**
| Muscle Group | Recovery Hours |
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
GET /analytics/recovery
Authorization: Bearer <token>

Response:
{
  "fatigued_muscles": [...],
  "last_workout_at": "2026-01-05T10:30:00"
}
```

### iOS Components

#### 1. API Types (`Services/APITypes.swift`)

```swift
struct RecoveryResponse: Codable {
    let fatiguedMuscles: [MuscleRecoveryStatus]
    let lastWorkoutAt: String?
}

struct MuscleRecoveryStatus: Codable, Identifiable {
    let muscleGroup: String
    let fantasyName: String
    let recoveryPercent: Double
    let hoursRemaining: Double
    let affectedExercises: [AffectedExercise]
}
```

#### 2. API Client (`Services/APIClient.swift`)

```swift
func getRecoveryStatus() async throws -> RecoveryResponse {
    return try await get("/analytics/recovery")
}
```

#### 3. Home View Model (`Views/Home/HomeViewModel.swift`)

Recovery status is fetched in parallel with other home screen data:

```swift
async let recoveryTask = APIClient.shared.getRecoveryStatus()
// ... other async tasks ...
recoveryStatus = recovery.fatiguedMuscles
```

#### 4. Recovery Card Component (`Components/RecoveryCard.swift`)

Visual design following the "System Window" style:
- Lightning bolt icon with cyan glow
- Holographic gradient border
- Grid layout for muscle cells
- Fill-up animation showing recovery progress
- Expandable to show affected exercises
- Fantasy-themed muscle names for gamification

#### 5. Home View Integration (`Views/Home/HomeView.swift`)

```swift
// Recovery Status Card - Only show if there are fatigued muscles
if !viewModel.recoveryStatus.isEmpty {
    RecoveryCard(recoveryData: viewModel.recoveryStatus)
        .padding(.horizontal)
}
```

## Design Decisions

### 1. Only Show When Relevant

The RecoveryCard only appears when there are fatigued muscles. This keeps the home screen clean when the user hasn't worked out recently.

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

This more accurately reflects real-world muscle recovery patterns.

### 4. Science-Based Recovery Times

Recovery times are based on muscle size and typical recovery research:
- Large muscles need more recovery time (72h)
- Small muscles recover faster (36h)

## Lessons Learned

### 1. API Response Format Matters

When designing the API response, we included both raw data (`muscleGroup`) and display data (`fantasyName`). This allows the iOS app to use the appropriate name based on context without needing a local mapping table.

### 2. Conditional UI Rendering

Instead of always showing the RecoveryCard with "No fatigued muscles" text, we chose to hide it entirely when empty. This reduces visual clutter and makes the home screen more dynamic.

### 3. Parallel Data Fetching

Using Swift's `async let` for parallel fetching significantly improves home screen load time:

```swift
// Good: Parallel fetching
async let recoveryTask = APIClient.shared.getRecoveryStatus()
async let workoutsTask = APIClient.shared.getWorkouts()

// Bad: Sequential fetching
let recovery = try await APIClient.shared.getRecoveryStatus()
let workouts = try await APIClient.shared.getWorkouts()
```

### 4. Exercise Name Normalization

Exercise names from user input can vary ("Bench Press", "bench press", "Barbell Bench Press"). The recovery service normalizes names to lowercase and checks for partial matches to handle variations.

### 5. Testing Challenges

Automated UI testing in iOS Simulator proved difficult due to:
- HealthKit permission dialogs blocking initial app launch
- Simulator touch input requiring specific tools (cliclick)
- Coordinate calculations for dynamic window positions

**Recommendation:** For future features, consider adding debug endpoints or test modes that can bypass permission dialogs.

## Files Changed

### Backend (3 new files)
- `backend/app/schemas/recovery.py`
- `backend/app/services/recovery_service.py`
- `backend/app/api/analytics.py` (modified - added recovery endpoint)

### iOS (5 files)
- `ios/FitnessApp/Services/APITypes.swift` (modified)
- `ios/FitnessApp/Services/APIClient.swift` (modified)
- `ios/FitnessApp/Views/Home/HomeViewModel.swift` (modified)
- `ios/FitnessApp/Views/Home/HomeView.swift` (modified)
- `ios/FitnessApp/Components/RecoveryCard.swift` (new)

## Testing

### Manual Testing Steps

1. Log a workout with mapped exercises (Bench Press, Squat, Deadlift, etc.)
2. Navigate to Home screen
3. RecoveryCard should appear showing fatigued muscles
4. Verify recovery percentages decrease over time
5. After 72 hours, all muscles should show 100% recovered

### API Testing

```bash
# Get recovery status (requires auth token)
curl -H "Authorization: Bearer <token>" \
  https://backend-production-e316.up.railway.app/analytics/recovery
```

## Future Improvements

1. **Push Notifications:** Notify users when muscles are fully recovered
2. **Workout Suggestions:** Recommend which muscle groups to train based on recovery
3. **Historical Recovery Data:** Track recovery patterns over time
4. **Custom Recovery Times:** Allow users to adjust recovery times based on their experience level
5. **Integration with Sleep/HRV:** Factor in sleep quality and HRV for more accurate recovery estimates
