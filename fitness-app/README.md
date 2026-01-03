# Fitness Tracker iOS App

A native iOS fitness tracking app for logging weight training workouts with comprehensive analytics.

## Overview

This app helps users track their strength training progress by:
- Logging workouts with weight, reps, RPE (Rate of Perceived Exertion), and RIR (Reps in Reserve)
- Calculating estimated 1RM (one-rep max) using multiple formulas
- Tracking progress trends over time with beautiful charts
- Comparing strength to population percentiles
- Providing personalized insights and recommendations
- Working fully offline with background sync

## Technology Stack

### Frontend
- **Framework**: SwiftUI (iOS 17+)
- **Local Storage**: SQLite via GRDB or SwiftData
- **Charts**: Swift Charts framework
- **Architecture**: MVVM with Combine/async-await

### Backend
- **Runtime**: Python 3.11+ with FastAPI
- **Database**: PostgreSQL (production), SQLite (development)
- **ORM**: SQLAlchemy 2.0
- **Auth**: JWT tokens
- **Analytics**: Custom analytics engine

## Project Structure

```
fitness-app/
├── ios/                    # iOS SwiftUI app
│   └── FitnessApp/
│       ├── Views/          # SwiftUI views
│       ├── ViewModels/     # MVVM view models
│       ├── Models/         # Data models
│       ├── Services/       # API and database services
│       └── Utils/          # Helpers and extensions
├── backend/                # FastAPI backend
│   ├── app/
│   │   ├── api/           # API endpoints
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── core/          # Config and security
│   │   └── services/      # Business logic
│   ├── main.py            # FastAPI app entry point
│   └── requirements.txt   # Python dependencies
├── feature_list.json      # Complete feature test suite (56 tests)
├── init.sh               # Setup and initialization script
└── README.md             # This file
```

## Quick Start

### Prerequisites

- **macOS**: Required for iOS development
- **Xcode 15+**: For SwiftUI and iOS 17+ support
- **Python 3.11+**: For backend development
- **PostgreSQL** (optional): SQLite used by default for development

### Setup

Run the initialization script to set up both frontend and backend:

```bash
./init.sh
```

This script will:
1. Check all prerequisites
2. Create Python virtual environment
3. Install backend dependencies
4. Create FastAPI project structure
5. Set up environment variables
6. Provide instructions for iOS project creation

### Running the Backend

```bash
# Option 1: Use the helper script
./start-backend.sh

# Option 2: Manual start
cd backend
source venv/bin/activate
python main.py
```

The API will be available at:
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc

### Running the iOS App

1. Open Xcode project:
   ```bash
   cd ios
   open FitnessApp.xcodeproj
   ```

2. Select a simulator or connected device

3. Press `Cmd+R` to build and run

## Core Features

### Workout Logging
- Create workout sessions with date and notes
- Search and add exercises from library
- Log sets with weight, reps, RPE, and RIR
- Quick-add buttons for common weight increments
- Copy previous workouts as templates
- Rest timer with notifications
- Auto-save progress locally

### Exercise Library
- 50+ pre-populated common exercises
- Exercise categories (Push, Pull, Legs, Core, Accessories)
- Muscle group tagging
- Custom exercise creation
- Favorite exercises for quick access

### Analytics & Charts
- e1RM progression line charts
- Weekly volume bar charts by muscle group
- Trend analysis (improving/stable/regressing)
- Automatic PR (personal record) detection
- Strength percentile comparisons
- Personalized insights and recommendations

### Offline & Sync
- Full offline functionality
- Local SQLite database
- Background sync when online
- Conflict resolution with device priority

## Development Progress

This project uses a test-driven development approach with comprehensive feature tracking.

### Feature Testing

The `feature_list.json` file contains 56 detailed end-to-end test cases covering:
- Backend API endpoints (auth, workouts, analytics, sync)
- iOS UI components (all 5 tab screens)
- Analytics calculations (e1RM, trends, percentiles)
- Offline functionality and sync
- Design system and UI polish
- Performance requirements

Each feature includes:
- Category (functional or style)
- Detailed description
- Step-by-step testing instructions
- Pass/fail status

### Checking Progress

```bash
# View all features
cat feature_list.json | jq '.[] | {description: .description, passes: .passes}'

# Count passing features
cat feature_list.json | jq '[.[] | select(.passes == true)] | length'

# View failing features
cat feature_list.json | jq '.[] | select(.passes == false) | .description'
```

## API Documentation

### Authentication
- `POST /auth/register` - Create new user account
- `POST /auth/login` - Login and get JWT token
- `POST /auth/refresh` - Refresh access token

### Profile
- `GET /profile` - Get user profile
- `PUT /profile` - Update profile (age, weight, preferences)

### Exercises
- `GET /exercises` - List all exercises (with search/filter)
- `POST /exercises` - Create custom exercise
- `GET /exercises/{id}` - Get exercise details

### Workouts
- `GET /workouts` - List workouts (paginated)
- `POST /workouts` - Create/sync workout
- `GET /workouts/{id}` - Get workout details
- `PUT /workouts/{id}` - Update workout
- `DELETE /workouts/{id}` - Delete workout

### Analytics
- `GET /analytics/exercise/{id}/trend` - Exercise trend data
- `GET /analytics/exercise/{id}/history` - Set history
- `GET /analytics/percentiles` - Strength percentiles
- `GET /analytics/prs` - Personal records
- `GET /analytics/weekly-review` - Weekly summary
- `GET /analytics/insights` - Personalized insights

### Bodyweight
- `GET /bodyweight` - Get bodyweight history
- `POST /bodyweight` - Log bodyweight entry

### Sync
- `POST /sync` - Bulk sync local changes
- `GET /sync/status` - Get sync status

## Design System

### Color Palette
- **Background**: `#0D0D0D` (near black)
- **Surface**: `#1A1A1A` (dark gray)
- **Card**: `#242424` (elevated surface)
- **Primary**: `#FF6B35` (vibrant orange - PRs, CTAs)
- **Secondary**: `#4ECDC4` (teal - secondary actions)
- **Success**: `#2ECC71` (green - improvements)
- **Warning**: `#F39C12` (amber - plateaus)
- **Danger**: `#E74C3C` (red - regressions)

### Typography
- **Headers**: SF Pro Display
- **Body**: SF Pro Text
- **Numbers**: SF Mono

### Components
- Rounded cards with subtle shadows
- Haptic feedback on interactions
- Smooth chart animations
- Pull-to-refresh with sync indicator

## Database Schema

### Core Tables
- `users` - User accounts
- `user_profiles` - User settings and body metrics
- `exercises` - Exercise library (seeded + custom)
- `workout_sessions` - Workout metadata
- `workout_exercises` - Exercises in a workout
- `sets` - Individual sets with weight, reps, RPE, RIR, e1RM
- `bodyweight_entries` - Body weight tracking
- `prs` - Personal records (e1RM and rep PRs)

See `app_spec.txt` for complete schema details.

## Contributing

This is an autonomous coding project. All development is tracked through:
1. `feature_list.json` - The single source of truth for features
2. `claude-progress.txt` - Session-by-session progress notes
3. Git commits - All changes committed with descriptive messages

### Development Workflow
1. Pick highest priority feature from `feature_list.json` with `"passes": false`
2. Implement feature following spec in `app_spec.txt`
3. Test thoroughly following steps in feature definition
4. Update feature to `"passes": true` only when fully complete
5. Commit changes with clear message
6. Move to next feature

## Future Enhancements

- Apple Health integration (export workouts, import body weight)
- Whoop integration (recovery scores, training readiness)
- Training program templates
- AI coaching recommendations
- Social features (share PRs)
- Apple Watch companion app

## License

This project is part of the Claude autonomous coding demonstration.

## Support

For questions or issues, refer to:
- `app_spec.txt` - Complete project specification
- `feature_list.json` - Feature testing checklist
- API docs at http://localhost:8000/docs
