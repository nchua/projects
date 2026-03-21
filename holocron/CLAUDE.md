# CLAUDE.md — Holocron

AI-powered spaced repetition system that builds itself from your existing knowledge sources.

## Project Structure

```
holocron/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes (auth, topics, concepts, learning_units, reviews, inbox)
│   │   ├── core/          # Config, database, security (JWT), FSRS engine
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   └── services/      # Business logic (future)
│   ├── alembic/           # Database migrations
│   ├── tests/             # Pytest test suite
│   ├── main.py            # FastAPI app entrypoint
│   ├── seed.py            # Sample data for development
│   └── requirements.txt
├── SPEC.md                # Full product specification
└── CLAUDE.md
```

## Commands

```bash
cd backend

# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run server
python main.py                    # localhost:8000, auto-reload

# Run tests
python -m pytest tests/ -v

# Database migrations
alembic upgrade head              # Apply migrations
alembic revision --autogenerate -m "desc"  # Create new migration

# Seed data
python seed.py                    # Creates test user + sample cards
```

## Key Architecture

- **FSRS Engine** (`app/core/fsrs.py`): Spaced repetition scheduler. Three-component memory model (stability, difficulty, retrievability). AI-generated cards get 18% shorter initial intervals.
- **Inbox System**: Cards with confidence >= 0.85 auto-accepted; below goes to inbox for manual review.
- **Auth**: JWT tokens via `python-jose`, passwords hashed with `passlib[bcrypt]`.

## Environment Variables

- `DATABASE_URL` — PostgreSQL connection string (Railway)
- `SECRET_KEY` — JWT signing key

## API Prefix

All endpoints under `/api/v1/`. Auth required for everything except `/health`, register, and login.
