"""Grant the owner unlimited screenshot scans (ARISE v3 spec §11).

Run from fitness-app/backend:
    SEED_USER_EMAIL=<owner email> venv/bin/python scripts/grant_owner_unlimited_scans.py

Sets ``scan_balances.has_unlimited = true`` for the user identified by
``SEED_USER_EMAIL`` (creating the balance row if missing). Idempotent — a
second run reports the row already unlimited. Never prints the email.
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.models  # noqa: E402, F401 — register every model
from app.models.scan_balance import ScanBalance  # noqa: E402
from app.models.user import User  # noqa: E402


def main() -> int:
    email = (os.environ.get("SEED_USER_EMAIL") or "").strip()
    if not email:
        print("SEED_USER_EMAIL not set — nothing to do")
        return 1
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL not set")
        return 1

    engine = create_engine(url)
    session = sessionmaker(bind=engine)()
    try:
        user = (
            session.query(User)
            .filter(User.email == email, User.is_deleted == False)
            .first()
        )
        if user is None:
            print("no active user matches SEED_USER_EMAIL")
            return 1

        balance = session.query(ScanBalance).filter(ScanBalance.user_id == user.id).first()
        created = balance is None
        if created:
            balance = ScanBalance(user_id=user.id)
            session.add(balance)
            session.flush()

        before = bool(balance.has_unlimited)
        balance.has_unlimited = True
        session.commit()

        print(f"user …{user.id[-4:]} scan balance {'created' if created else 'found'}")
        print(f"has_unlimited before={before} after={bool(balance.has_unlimited)} "
              f"credits={balance.scan_credits}")
        if before:
            print("already unlimited — no change")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
