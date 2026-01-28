# Screenshot Processing Feature

## Overview

The fitness app supports importing workout data from screenshots using Claude Vision API. Users can select one or multiple workout screenshots from their photo library, and the system will:

1. Extract workout data (exercises, sets, reps, weights) using Claude Vision
2. Match extracted exercise names to the database using fuzzy matching
3. Auto-save the workout to the database (with XP, PR detection, quest progress)
4. Return structured data for display in the app

## Architecture

```
iOS App                          Backend (FastAPI on Railway)
─────────                        ───────────────────────────
ScreenshotPickerView             POST /screenshot/process
        │                                  │
        ▼                                  ▼
ScreenshotProcessingViewModel    screenshot_service.py
        │                        ├── extract_workout_from_screenshot()
        ▼                        │   └── Calls Claude Vision API
ScreenshotPreviewView            ├── match_exercise_names()
        │                        │   └── Fuzzy matching with rapidfuzz
        ▼                        └── save_extracted_workout()
LogView (workout logged)             └── Creates WorkoutSession, Sets, PRs
```

## Backend Implementation

### Files

| File | Purpose |
|------|---------|
| `app/api/screenshot.py` | API endpoints for screenshot processing |
| `app/services/screenshot_service.py` | Core extraction and saving logic |
| `app/schemas/screenshot.py` | Pydantic models for request/response |

### API Endpoints

#### `POST /screenshot/process`

Process a single screenshot.

**Form Parameters:**
- `file` (required): Image file (PNG, JPEG, GIF, WebP)
- `save_workout` (optional, default: false): Auto-save as workout
- `session_date` (optional): Override date in YYYY-MM-DD format
- `include_warmups` (optional, default: true): Include warmup sets

**Response:**
```json
{
  "session_date": "2026-01-03",
  "session_name": "LEGS + BICEPS",
  "duration_minutes": 59,
  "summary": {
    "tonnage_lb": 14555,
    "total_reps": 117
  },
  "exercises": [
    {
      "name": "Back Squat",
      "equipment": "barbell",
      "sets": [
        {"weight_lb": 135, "reps": 8, "sets": 1, "is_warmup": true},
        {"weight_lb": 235, "reps": 5, "sets": 5, "is_warmup": false}
      ],
      "matched_exercise_id": "4babb07f-8d56-46ce-b6e2-6dd82f8d179a",
      "matched_exercise_name": "Back Squat",
      "match_confidence": 100
    }
  ],
  "processing_confidence": "high",
  "workout_id": "603ca540-de2d-426f-88ff-93dc4cad9bfe",
  "workout_saved": true
}
```

#### `POST /screenshot/process/batch`

Process multiple screenshots and combine into one workout.

**Form Parameters:**
- `files` (required): Multiple image files (max 10)
- `save_workout` (optional, default: true): Auto-save combined workout
- `session_date` (optional): Override date
- `include_warmups` (optional, default: true): Include warmup sets

**Response:** Same as single, plus:
```json
{
  "screenshots_processed": 3,
  ...
}
```

### Key Functions in `screenshot_service.py`

```python
async def extract_workout_from_screenshot(
    image_data: bytes,
    filename: str,
    db: Session,
    user_id: str
) -> Dict[str, Any]:
    """
    Uses Claude Vision API to extract workout data from a screenshot.
    Returns structured data with exercises matched to database.
    """

def merge_extractions(extractions: List[Dict]) -> Dict[str, Any]:
    """
    Combines multiple screenshot extractions into one.
    - Takes session info from first extraction that has it
    - Combines all exercises into one list
    - Sums up tonnage and reps
    """

async def save_extracted_workout(
    db: Session,
    user_id: str,
    extraction_result: Dict,
    session_date: Optional[datetime] = None,
    include_warmups: bool = True
) -> str:
    """
    Saves extracted workout to database.
    - Creates WorkoutSession
    - Creates WorkoutExercise and Set records
    - Calculates E1RM for each set
    - Detects and creates PRs
    - Awards XP
    - Updates quest progress
    - Checks achievements
    Returns: workout_id
    """
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for Vision extraction |
| `DATABASE_URL` | Yes | PostgreSQL connection string |

## iOS Implementation

### Files

| File | Purpose |
|------|---------|
| `Services/APIClient.swift` | API calls including batch processing |
| `Services/APITypes.swift` | Response models |
| `Views/Log/ScreenshotPickerView.swift` | Photo picker with multi-select |
| `Views/Log/ScreenshotProcessingViewModel.swift` | Processing state management |
| `Views/Log/ScreenshotPreviewView.swift` | Results display and confirmation |
| `Views/Log/LogView.swift` | Main log view that triggers flow |

### User Flow

1. User taps camera icon in LogView
2. `ScreenshotPickerView` presents with options:
   - "TAKE PHOTO" - Camera capture
   - "SELECT SCREENSHOTS" - Photo library (multi-select up to 10)
3. Selected images are compressed and passed to `ScreenshotProcessingViewModel`
4. ViewModel calls appropriate API:
   - 1 image → `processScreenshot()`
   - 2+ images → `processScreenshotsBatch()`
5. `ScreenshotPreviewView` shows results:
   - Processing animation while waiting
   - Error view with retry if failed
   - Results view with exercises, sets, confidence
   - "WORKOUT SAVED" confirmation if auto-saved
6. User taps "DONE" to close

### Key Types

```swift
// Response from single screenshot
struct ScreenshotProcessResponse: Decodable {
    let sessionDate: String?
    let sessionName: String?
    let durationMinutes: Int?
    let summary: ExtractedSummary?
    let exercises: [ExtractedExercise]
    let processingConfidence: String
    let workoutId: String?      // Present if saved
    let workoutSaved: Bool
}

// Response from batch processing
struct ScreenshotBatchResponse: Decodable {
    let screenshotsProcessed: Int
    let sessionDate: String?
    let sessionName: String?
    let durationMinutes: Int?
    let summary: ExtractedSummary?
    let exercises: [ExtractedExercise]
    let processingConfidence: String
    let workoutId: String?
    let workoutSaved: Bool
}
```

### ViewModel State

```swift
class ScreenshotProcessingViewModel: ObservableObject {
    @Published var isProcessing = false
    @Published var processedData: ScreenshotProcessResponse?
    @Published var batchData: ScreenshotBatchResponse?
    @Published var error: String?
    @Published var selectedImagesData: [Data] = []  // Multi-image support
    @Published var workoutSaved = false
    @Published var savedWorkoutId: String?

    var isBatchMode: Bool { selectedImagesData.count > 1 }
    var imageCount: Int { selectedImagesData.count }
}
```

## Claude Vision Prompt

The extraction prompt in `screenshot_service.py`:

```python
EXTRACTION_PROMPT = """Analyze this workout screenshot from a fitness tracking app.

Extract the following information in JSON format:
{
  "session_date": "YYYY-MM-DD or null",
  "session_name": "workout name/title or null",
  "duration_minutes": number or null,
  "summary": {
    "tonnage_lb": total weight lifted or null,
    "total_reps": total reps or null
  },
  "exercises": [
    {
      "name": "exercise name",
      "equipment": "barbell/dumbbell/machine/bodyweight/cable",
      "variation": "any variation like 'incline' or null",
      "sets": [
        {
          "weight_lb": weight in pounds,
          "reps": number of reps,
          "sets": number of sets at this weight/rep (default 1),
          "is_warmup": true if warmup set
        }
      ]
    }
  ]
}

Important:
- Extract ALL exercises visible in the screenshot
- Identify warmup sets (lower weight, marked as warmup)
- Convert kg to lb if needed (1 kg = 2.205 lb)
- Return valid JSON only, no markdown
"""
```

## Exercise Matching

Uses `rapidfuzz` for fuzzy string matching:

```python
def match_exercise_to_library(
    extracted_name: str,
    equipment: Optional[str],
    db: Session
) -> Tuple[Optional[str], Optional[str], int]:
    """
    Returns: (exercise_id, matched_name, confidence_score)

    Matching strategy:
    1. Query exercises from database
    2. Build searchable strings: "name equipment variation"
    3. Use rapidfuzz.process.extractOne with scorer=fuzz.WRatio
    4. Return best match if score >= 60
    """
```

## Database Models Affected

```python
# Created by save_extracted_workout()
WorkoutSession(
    user_id=user_id,
    date=workout_date,
    duration_minutes=duration,
    notes="Session Name - Imported from screenshot"
)

WorkoutExercise(
    session_id=workout_session.id,
    exercise_id=matched_exercise_id,
    order_index=0
)

Set(
    workout_exercise_id=workout_exercise.id,
    weight=235.0,
    weight_unit=WeightUnit.LB,
    reps=5,
    set_number=1,
    e1rm=274.17  # Calculated using user's preferred formula
)
```

## Testing

### Backend (curl)

```bash
# Single screenshot
curl -X POST "https://backend-production-e316.up.railway.app/screenshot/process" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@workout.png" \
  -F "save_workout=true"

# Multiple screenshots
curl -X POST "https://backend-production-e316.up.railway.app/screenshot/process/batch" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@workout1.png" \
  -F "files=@workout2.png" \
  -F "files=@workout3.png" \
  -F "save_workout=true" \
  -F "session_date=2026-01-03"
```

### iOS

1. Build and run on simulator
2. Log in with test account
3. Go to Log tab
4. Tap camera icon
5. Select 2-3 workout screenshots
6. Verify extraction results
7. Check workout appears in History

## Common Issues

### "ANTHROPIC_API_KEY environment variable not set"
- Add key to Railway: `railway variables --set "ANTHROPIC_API_KEY=sk-ant-..."`
- Redeploy: `railway up`

### Exercise not matched
- Check if exercise exists in database
- Verify spelling is close enough (>60% fuzzy match)
- Add missing exercises via `/exercises` endpoint

### Timeout on batch processing
- Backend timeout is 120 seconds for batch
- iOS timeout is 120 seconds
- Consider reducing number of screenshots if consistently timing out

## Future Improvements

1. **Parallel processing**: Process multiple screenshots concurrently instead of sequentially
2. **Duplicate detection**: Skip exercises already extracted from previous screenshots
3. **Manual matching UI**: Let user manually match unmatched exercises
4. **Offline queue**: Queue screenshots for processing when offline
5. **Progress streaming**: Show per-screenshot progress during batch processing
