#!/usr/bin/env python3
"""
One-time import of the training-calendar PWA plan into the owner's Campaign
(ARISE v3 spec §4.3).

Reads ``../../training-calendar/data.js`` (relative to this repo's backend),
strips the ``const PHASES =`` wrapper and trailing ``;`` — the file is
JSON-compatible after that — logs in as the owner and POSTs the phases to
``/campaign/import``. Prints the response summary and warnings. Never prints
credentials.

Usage:
    SEED_USER_EMAIL=... SEED_USER_PASSWORD=... \\
    venv/bin/python scripts/import_training_calendar.py [--name NAME] \\
        [--start-date YYYY-MM-DD] [--goal TEXT] [--replace] [--dry-run]

    API_BASE_URL defaults to the Railway backend.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv

# Same convention as the other owner scripts: SEED_USER_EMAIL (and DATABASE_URL)
# come from backend/.env; SEED_USER_PASSWORD is passed on the command line.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_BASE_URL = "https://backend-production-e316.up.railway.app"
DATA_JS = Path(__file__).resolve().parents[3] / "training-calendar" / "data.js"
TIMEOUT = 60.0


def load_phases(path: Path = DATA_JS) -> List[Dict[str, Any]]:
    """Parse ``data.js`` into the PHASES list."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)          # header comment
    match = re.search(r"const\s+PHASES\s*=\s*", text)
    if not match:
        raise ValueError(f"{path}: no `const PHASES =` found")
    body = text[match.end():].strip()
    if body.endswith(";"):
        body = body[:-1].rstrip()
    phases = json.loads(body)
    if not isinstance(phases, list) or not phases:
        raise ValueError(f"{path}: PHASES is not a non-empty list")
    return phases


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", default="Run Base + Strength", help="Campaign name")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD (default: Monday of this week)")
    parser.add_argument("--goal", default=None, help="Campaign goal text")
    parser.add_argument("--replace", action="store_true", help="Retire the active campaign first")
    parser.add_argument("--dry-run", action="store_true", help="Parse data.js and print the payload only")
    parser.add_argument("--data", default=str(DATA_JS), help="Path to data.js")
    args = parser.parse_args(argv)

    phases = load_phases(Path(args.data))
    payload: Dict[str, Any] = {
        "name": args.name,
        "phases": phases,
        "client_date": date.today().isoformat(),
        "replace": bool(args.replace),
    }
    if args.start_date:
        payload["start_date"] = args.start_date
    if args.goal:
        payload["goal"] = args.goal

    print(f"Loaded {len(phases)} phases, {sum(len(p.get('days', [])) for p in phases)} days from {args.data}")
    if args.dry_run:
        print(json.dumps({k: v for k, v in payload.items() if k != "phases"}, indent=2))
        for phase in phases:
            print(f"  {phase.get('label')}: {phase.get('milesMin')}–{phase.get('milesMax')} mi/wk, long {phase.get('longRunMi')}")
        return 0

    email = os.environ.get("SEED_USER_EMAIL")
    password = os.environ.get("SEED_USER_PASSWORD")
    if not email or not password:
        print("Set SEED_USER_EMAIL and SEED_USER_PASSWORD in the environment.", file=sys.stderr)
        return 2
    base_url = os.environ.get("API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    with httpx.Client(base_url=base_url, timeout=TIMEOUT) as client:
        login = client.post("/auth/login", json={"email": email, "password": password})
        if login.status_code != 200:
            print(f"Login failed: HTTP {login.status_code}", file=sys.stderr)
            return 1
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = client.post("/campaign/import", json=payload, headers=headers)
        if resp.status_code == 409:
            print("An active campaign already exists — rerun with --replace to retire it.", file=sys.stderr)
            return 1
        if resp.status_code != 201:
            print(f"Import failed: HTTP {resp.status_code} {resp.text[:500]}", file=sys.stderr)
            return 1

    body = resp.json()
    print(f"Campaign {body['id']} — {body['name']}")
    print(f"  start {body['start_date']} → end {body['end_date']} · status {body['status']}")
    print(f"  arcs: {len(body['arcs'])} · templates created: {body.get('templates_created')}")
    for arc in body["arcs"]:
        print(f"    [{arc['index'] + 1}] {arc['name']}: {arc['weeks']} wk · "
              f"{arc['run_miles_min']}–{arc['run_miles_max']} mi/wk · long {arc['long_run_miles']} · "
              f"{len(arc['templates'])} templates")
    if body.get("current_arc_index") is not None:
        print(f"  now: arc {body['current_arc_index'] + 1}, week {body['week_in_arc']}"
              f"{' (deload)' if body.get('deload_week') else ''} · target {body.get('week_target_miles')} mi")
    warnings = body.get("warnings") or []
    print(f"  warnings: {len(warnings)}")
    for w in warnings:
        print(f"    - {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
