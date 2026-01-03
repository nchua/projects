# FitnessApp iOS

Native iOS fitness tracking app built with SwiftUI.

## Current Status

**All Swift source code has been created!** The app includes:
- Complete MVVM architecture with ViewModels for each screen
- 5-tab navigation (Home, Log, History, Progress, Profile)
- API client with all endpoints
- SwiftData models for local storage
- Swift Charts integration for progress visualization
- Dark theme color system
- All major screens implemented

## Project Structure

```
FitnessApp/
├── FitnessApp.swift    # Main app entry with SwiftData
├── Views/              # SwiftUI views
│   ├── ContentView.swift  # Tab navigation + Auth
│   ├── Home/          # Dashboard with stats, PRs, insights
│   ├── Log/           # Workout logging with exercise picker
│   ├── History/       # Calendar view and workout list
│   ├── Progress/      # Charts for strength & bodyweight
│   └── Profile/       # User settings and bodyweight logging
├── Models/            # SwiftData models
│   ├── User.swift
│   ├── Exercise.swift
│   ├── Workout.swift
│   ├── BodyweightEntry.swift
│   └── PersonalRecord.swift
├── Services/          # API client and auth
│   ├── APIClient.swift
│   ├── APITypes.swift
│   └── AuthManager.swift
└── Utils/             # Helpers and extensions
    ├── Colors.swift
    └── Extensions.swift
```

## Setup

### Prerequisites
- Xcode 15 or later
- macOS Sonoma or later
- iOS 17+ SDK

### Creating the Xcode Project

1. Open Xcode
2. File → New → Project
3. Select "iOS" → "App"
4. Configure:
   - Product Name: `FitnessApp`
   - Team: Your team
   - Organization Identifier: `com.yourcompany`
   - Interface: **SwiftUI**
   - Language: **Swift**
   - Storage: **SwiftData**
   - Include Tests: Yes
5. Save in this `ios/` directory (replace the default ContentView.swift)

### Integrating the Existing Swift Files

After creating the Xcode project, integrate the existing Swift files:

1. **Delete default files**: Remove the auto-generated `ContentView.swift` and `FitnessAppApp.swift`

2. **Add existing files to project**:
   - In Xcode, right-click on the `FitnessApp` folder in the navigator
   - Select "Add Files to 'FitnessApp'..."
   - Navigate to the `FitnessApp/` folder containing the Swift files
   - Select all `.swift` files and folders (Models, Views, Services, Utils)
   - Check "Copy items if needed" and "Create groups"
   - Click "Add"

3. **Verify file structure**:
   - Ensure all 22 Swift files are added to the project
   - Build the project (Cmd+B) to verify there are no errors

4. **Add required frameworks**:
   - Charts framework is included automatically with iOS 16+
   - SwiftData is included automatically with iOS 17+

### Dependencies

Consider adding these Swift packages:
- **GRDB** (if not using SwiftData): https://github.com/groue/GRDB.swift
  - For robust SQLite database management
- **Alamofire** (optional): For advanced networking
  - Native URLSession is sufficient for this project

### Project Organization

Organize files within Xcode using groups that match the directory structure above.

## Key Features to Implement

### 1. Main Tab Bar (ContentView.swift)
- 5 tabs: Home, Log, History, Progress, Profile
- Each tab has its own view and view model

### 2. Database Layer
- Local SQLite storage using SwiftData or GRDB
- Models matching backend schema:
  - User, UserProfile
  - Exercise, WorkoutSession, WorkoutExercise, Set
  - BodyweightEntry, PR (Personal Record)
- CRUD operations and queries
- Sync queue for offline changes

### 3. API Service
- REST client for backend communication
- JWT token management
- Request/response models
- Error handling
- Background sync

### 4. Analytics Engine
- e1RM calculations (Epley, Brzycki, Wathan, Lombardi)
- Trend analysis
- PR detection
- Percentile comparisons

### 5. Charts
- Swift Charts for visualizations
- e1RM progression line charts
- Volume bar charts
- Percentile gauges

## Design System

### Colors
Define in `Utils/Colors.swift`:
```swift
extension Color {
    static let appBackground = Color(hex: "0D0D0D")
    static let appSurface = Color(hex: "1A1A1A")
    static let appCard = Color(hex: "242424")
    static let appPrimary = Color(hex: "FF6B35")
    static let appSecondary = Color(hex: "4ECDC4")
    static let appSuccess = Color(hex: "2ECC71")
    static let appWarning = Color(hex: "F39C12")
    static let appDanger = Color(hex: "E74C3C")
}
```

### Typography
Use native SF Pro fonts:
- `.title`, `.title2`, `.title3` for headers
- `.body`, `.callout` for content
- `.footnote`, `.caption` for secondary text
- Custom modifier for monospaced numbers

### Components
Create reusable components in `Views/Components/`:
- `CardView` - Rounded cards with shadow
- `StatCard` - Quick stat display
- `ExercisePicker` - Searchable exercise selector
- `SetRow` - Set logging form row
- `ChartCard` - Wrapper for charts
- `PRBadge` - PR celebration badge

## Running the App

1. Open `FitnessApp.xcodeproj` in Xcode
2. Select target device/simulator (iOS 17+)
3. Press `Cmd+R` to build and run

## Testing

- Unit tests: `FitnessAppTests/`
- UI tests: `FitnessAppUITests/`
- Test targets are created automatically by Xcode

## Backend Connection

Update API base URL in `Services/API/APIClient.swift`:
```swift
let baseURL = "http://localhost:8000"  // Development
// let baseURL = "https://api.yourapp.com"  // Production
```

For iOS simulator to connect to localhost backend:
- Use `http://localhost:8000` (simulator runs on same machine)
- For physical device testing, use computer's local IP: `http://192.168.x.x:8000`
