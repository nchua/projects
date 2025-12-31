# FitnessApp iOS

Native iOS fitness tracking app built with SwiftUI.

## Project Structure

```
FitnessApp/
├── Views/              # SwiftUI views
│   ├── Home/          # Dashboard and home screen
│   ├── Log/           # Workout logging interface
│   ├── History/       # Past workouts and calendar
│   ├── Progress/      # Charts and analytics
│   ├── Profile/       # User settings and profile
│   └── Components/    # Reusable UI components
├── ViewModels/        # MVVM view models
├── Models/            # Data models
├── Services/          # API client and database services
│   ├── API/           # Network layer
│   └── Database/      # Local SQLite/SwiftData
└── Utils/             # Helpers, extensions, constants
```

## Setup

### Prerequisites
- Xcode 15 or later
- macOS Sonoma or later
- iOS 17+ SDK

### Creating the Project

1. Open Xcode
2. File → New → Project
3. Select "iOS" → "App"
4. Configure:
   - Product Name: `FitnessApp`
   - Team: Your team
   - Organization Identifier: `com.yourcompany`
   - Interface: **SwiftUI**
   - Language: **Swift**
   - Storage: **SwiftData** (or use GRDB for SQLite)
   - Include Tests: Yes
5. Save in this `ios/` directory

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
