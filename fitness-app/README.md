# Solo Leveling Themed Fitness App

A gamified iOS fitness tracking app inspired by *Solo Leveling*, with a FastAPI backend and Claude Vision AI integration for screenshot-based workout logging.

## Features

### Workout Tracking
- Manual workout logging with weight, reps, RPE, and RIR
- AI screenshot processing — snap a photo of your gym app and Claude Vision extracts the workout data
- WHOOP activity screenshot support (strain, HR zones, calories)
- 50+ pre-populated exercises with custom exercise creation
- Estimated 1RM calculation using the Epley formula
- Superset support for paired exercises

### Gamification
- XP system with level progression (100 x level^1.5 per level)
- Hunter rank badges from E-rank to S-rank
- Daily quests — 5 quest types generated each day based on training history
- Dungeon gates — multi-day challenges with objectives, time limits, and difficulty ranks
- Streak tracking, achievements, and PR celebration animations

### Analytics
- e1RM progression charts (Swift Charts)
- Strength percentile comparisons for 20+ exercises against population standards
- Trend analysis — improving, stable, or regressing per lift
- Automatic personal record detection across rep ranges
- Weekly review summaries with volume and exercise variety stats
- AI-generated training insights

### Social
- Friend system with requests and hunter profiles
- Competitive stats (XP, level, rank, recent workouts)

### Architecture
- Offline-first with local SwiftData storage and background sync
- JWT authentication with token refresh
- Deployed on Railway with auto-deploy from `main`

## Screenshots

Interactive HTML mockups of each screen: **[View all mockups](https://nickchua.me/projects/fitness-app/)**

| Screen | Description |
|--------|-------------|
| [Home](https://nickchua.me/projects/fitness-app/home.html) | Hunter status, daily quests, power levels |
| [Quests](https://nickchua.me/projects/fitness-app/quests.html) | Quest center with calendar and archive |
| [Workout Log](https://nickchua.me/projects/fitness-app/log.html) | Active session with exercise tracking |
| [Stats](https://nickchua.me/projects/fitness-app/stats.html) | e1RM charts, percentiles, trends |
| [History](https://nickchua.me/projects/fitness-app/history.html) | Calendar view with workout details |
| [Dungeons](https://nickchua.me/projects/fitness-app/dungeons.html) | Gate board with objectives and rewards |
| [Friends](https://nickchua.me/projects/fitness-app/friends.html) | Hunter network with rank and streaks |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| iOS | SwiftUI (iOS 17+), SwiftData, Swift Charts, MVVM |
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL (production), SQLite (development) |
| AI | Anthropic Claude Vision API |
| Auth | JWT (python-jose, bcrypt) |
| Deployment | Railway (auto-deploy from `main`) |

## Project Structure

```
fitness-app/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── api/               # Endpoints (auth, workouts, exercises,
│   │   │                      #   analytics, quests, dungeons, friends,
│   │   │                      #   screenshot, sync, profile, bodyweight)
│   │   ├── core/              # Config, security, database, e1RM engine
│   │   ├── models/            # SQLAlchemy models
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   └── services/          # Screenshot processing, quest generation
│   ├── alembic/               # Database migrations
│   └── main.py
├── ios/                        # iOS SwiftUI app
│   └── FitnessApp/
│       ├── Views/             # SwiftUI views (Home, Log, Quests,
│       │                      #   History, Stats, Profile, Dungeons, Friends)
│       ├── Services/          # APIClient, AuthManager, HealthKitManager
│       ├── Models/            # Data models and SwiftData schemas
│       ├── Components/        # Reusable UI (XPBar, RankBadge, PRCelebration)
│       └── Utils/             # Colors, Fonts, Extensions
├── mockups/                    # Interactive HTML screen mockups
├── docs/                       # Technical documentation
│   ├── screenshot-processing.md
│   ├── healthkit-integration.md
│   └── development/           # Session notes and progress logs
└── init.sh                     # Setup script
```

## API Overview

| Group | Endpoints | Description |
|-------|-----------|-------------|
| Auth | `/auth/register`, `/auth/login`, `/auth/refresh` | Account creation and JWT tokens |
| Workouts | CRUD on `/workouts` | Workout sessions with exercises and sets |
| Exercises | `/exercises`, `/exercises/search` | Exercise library with search and filtering |
| Analytics | `/analytics/*` | e1RM trends, strength percentiles, PRs, weekly reviews, insights |
| Screenshots | `/screenshot/process`, `/screenshot/batch` | Claude Vision workout extraction |
| Quests | `/quests`, `/quests/{id}/claim` | Daily quest generation and claiming |
| Dungeons | `/dungeons/*` | Gate system — accept, progress, claim rewards |
| Friends | `/friends/*` | Friend requests, profiles, competitive data |
| Profile | `/profile` | User settings, bodyweight, XP and rank |
| Sync | `/sync` | Offline-first bulk sync |
| Bodyweight | `/bodyweight` | Bodyweight logging and history |

## Database Schema

### Core
`users`, `user_profiles`, `exercises`, `workout_sessions`, `workout_exercises`, `sets`, `bodyweight_entries`, `prs`

### Gamification
`quest_definitions`, `user_quests`, `dungeon_definitions`, `user_dungeons`, `user_dungeon_objectives`, `achievements`, `user_achievements`

### Social
`friends`, `friend_requests`

## Quick Start

### Prerequisites
- macOS with Xcode 15+
- Python 3.11+
- PostgreSQL (optional — SQLite used for development)

### Setup

```bash
./init.sh
```

### Backend

```bash
cd backend
source venv/bin/activate
python main.py
```

API available at `http://localhost:8000/docs`

### iOS

```bash
cd ios
xcodegen generate
open FitnessApp.xcodeproj
# Build and run with Cmd+R
```

## Design System

The app uses the **Edge Flow** design language — a dark, high-contrast aesthetic built for readability during workouts.

| Token | Hex | Usage |
|-------|-----|-------|
| Void | `#050508` | Deepest background |
| Card | `#0f1018` | Card surfaces |
| Elevated | `#141520` | Headers, elevated content |
| Primary | `#00D4FF` | Main accent (cyan) |
| Success | `#00FF88` | Completed states |
| Gold | `#FFD700` | Achievements, A-rank |
| Danger | `#FF4757` | Warnings, S-rank |

Typography uses four font families: **Orbitron** (display), **Rajdhani** (headers), **Inter** (body), and **JetBrains Mono** (system/metrics).
