# Arise Fitness Tracker

A gamified iOS fitness app inspired by *Solo Leveling* — with AI-powered workout logging, personalized coaching, and strength analytics.

![SwiftUI](https://img.shields.io/badge/SwiftUI-iOS_17+-007AFF?style=flat-square&logo=swift&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Python_3.11+-009688?style=flat-square&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Claude Vision](https://img.shields.io/badge/Claude_Vision-AI-D97706?style=flat-square&logo=anthropic&logoColor=white)

**[View interactive mockups &rarr;](https://nickchua.me/projects/fitness-app/)**

---

## Features

### AI Screenshot Processing
Snap a photo of your gym app and Claude Vision extracts the full workout — exercises, sets, weights, and reps — in seconds. Supports both workout tracker screenshots and WHOOP activity data (strain, HR zones, calories). The extraction pipeline handles messy real-world screenshots with fuzzy exercise matching against a 50+ exercise library, then saves structured data to the backend in a single flow.

### Coaching & Goals
Set up to 5 concurrent strength goals (e.g., "bench 225 lbs by March 15") and receive weekly missions with personalized workout prescriptions. The system auto-detects your training split (Push/Pull/Legs, Upper/Lower, Full Body), calculates target weights from your current estimated 1RM, and tracks pace toward each goal with weekly progress reports and AI-generated coaching insights.

### Gamification
A full RPG progression system layered on top of real training data. Earn XP for logging workouts, hitting PRs, and completing quests. Level up through hunter ranks from E-rank to S-rank. Daily quests rotate based on your training history, and multi-day dungeon challenges push you toward specific objectives with time limits, difficulty tiers, and ranked rewards.

### Strength Analytics
Estimated 1RM progression charts (Swift Charts) for every lift, with trend analysis showing whether you're improving, stable, or regressing. Strength percentile rankings compare your numbers against population standards for 20+ exercises. Automatic PR detection fires across all rep ranges, and weekly review summaries break down volume, exercise variety, and training insights.

---

## Architecture & Tech Decisions

**SwiftUI + MVVM** — The entire iOS app is built in SwiftUI targeting iOS 17+. SwiftData provides offline-first local storage with background sync, so workouts are never lost to network issues. Swift Charts powers the analytics views.

**FastAPI + SQLAlchemy** — Python was chosen for the backend to leverage the Anthropic SDK for screenshot processing. FastAPI gives async endpoint handling with automatic OpenAPI docs. SQLAlchemy 2.0 with Alembic migrations manages a PostgreSQL database with 20+ models.

**Claude Vision for OCR** — Rather than building a custom ML pipeline for screenshot extraction, the app sends gym app screenshots to Claude Vision and parses the structured response. This handles the long tail of different gym apps, layouts, and edge cases far better than traditional OCR. Rate limited to 20 screenshots/day per user with a 10-second cooldown.

**JWT Auth with Refresh Tokens** — Access tokens expire in 1 hour, refresh tokens in 7 days. The iOS client handles automatic token refresh and session expiry gracefully.

---

## Technical Highlights

- **e1RM engine** — Epley formula (`weight * (1 + reps/30)`) calculated server-side on every set, driving PR detection, percentile rankings, and goal progress tracking
- **AI coaching pipeline** — Goals feed into a mission generator that produces weekly workout prescriptions with target weights calculated from current e1RM, then tracks pace (ahead/on-track/behind) with projected completion dates
- **Gamification math** — XP curve uses `100 * level^1.5` per level, with 5 quest types generated daily based on training history and current capabilities
- **Offline-first sync** — SwiftData local storage with background sync ensures workouts are saved immediately, then reconciled with the server
- **Screenshot extraction** — Claude Vision processes gym app screenshots into structured workout data with fuzzy exercise matching against the canonical exercise library
- **Dungeon system** — Multi-day challenges with objectives, time limits, difficulty ranks (E through S), and XP rewards tied to completion percentage

---

## Project Scale

- **20+ API endpoints** across auth, workouts, exercises, analytics, coaching, quests, dungeons, friends, screenshots, and sync
- **20+ database models** spanning core workout tracking, coaching, gamification, and social features
- **50+ exercises** pre-populated with muscle groups, equipment, and aliases for fuzzy matching
- **iOS 17+** with SwiftUI, SwiftData, Swift Charts, and MVVM architecture
- **Deployed on Railway** with auto-deploy from `main`

---

<details>
<summary><strong>Quick Start</strong></summary>

### Prerequisites
- macOS with Xcode 15+
- Python 3.11+
- PostgreSQL (optional — SQLite used for development)

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
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

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | JWT signing key |
| `ANTHROPIC_API_KEY` | Claude Vision API key |

</details>

<details>
<summary><strong>Design System — Edge Flow</strong></summary>

A dark, high-contrast aesthetic built for readability during workouts.

| Token | Hex | Usage |
|-------|-----|-------|
| Void | `#050508` | Deepest background |
| Card | `#0f1018` | Card surfaces |
| Elevated | `#141520` | Headers, elevated content |
| Primary | `#00D4FF` | Main accent (cyan) |
| Success | `#00FF88` | Completed states |
| Gold | `#FFD700` | Achievements, A-rank |
| Danger | `#FF4757` | Warnings, S-rank |

Typography: **Orbitron** (display), **Rajdhani** (headers), **Inter** (body), **JetBrains Mono** (metrics).

All card corners use 20px radius. Full-bleed gradient headers on primary screens.

</details>
