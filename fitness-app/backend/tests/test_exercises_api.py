"""
API-level tests for GET /exercises, focused on how canonical groups collapse
to a single picker entry.

The iOS exercise picker loads the whole list once and filters client-side, so
whichever name wins the collapse is the only name a user can find. Picking the
longest name meant the bilateral RDL surfaced as "Stiff-Leg Deadlift" and
"Romanian Deadlift" was unsearchable — leaving "Single Leg Romanian Deadlift"
as the only RDL in the app.
"""
import uuid

import pytest

from app.models.exercise import Exercise


@pytest.fixture
def seed_group(db):
    """Insert a canonical exercise plus its aliases, sharing one canonical_id."""
    def _seed(name: str, aliases: list, category: str = "Pull", primary_muscle: str = "Hamstrings"):
        canonical_id = str(uuid.uuid4())
        for row_name in [name, *aliases]:
            db.add(Exercise(
                id=str(uuid.uuid4()),
                name=row_name,
                canonical_id=canonical_id,
                category=category,
                primary_muscle=primary_muscle,
                secondary_muscles=[],
                is_custom=False,
                user_id=None,
            ))
        db.commit()
        return canonical_id

    return _seed


def _names(client, headers):
    response = client.get("/exercises", headers=headers)
    assert response.status_code == 200, response.text
    return [ex["name"] for ex in response.json()]


def test_canonical_name_wins_over_longer_alias(client, auth_headers, seed_group):
    """"Romanian Deadlift" represents its group, not the longer "Stiff-Leg Deadlift"."""
    headers, _ = auth_headers()
    seed_group("Romanian Deadlift", ["RDL", "Stiff-Leg Deadlift"])

    names = _names(client, headers)

    assert "Romanian Deadlift" in names
    assert "Stiff-Leg Deadlift" not in names
    assert "RDL" not in names


def test_both_romanian_deadlift_variants_are_listed(client, auth_headers, seed_group):
    """Barbell (two-leg) and single-leg RDL are distinct, separately loggable entries."""
    headers, _ = auth_headers()
    seed_group("Romanian Deadlift", ["RDL", "Stiff-Leg Deadlift"])
    seed_group("Single Leg Romanian Deadlift", ["Single Leg RDL", "SL RDL", "One Leg RDL"])

    names = _names(client, headers)

    assert "Romanian Deadlift" in names
    assert "Single Leg Romanian Deadlift" in names
    assert len([n for n in names if "Romanian" in n]) == 2


def test_search_finds_both_romanian_deadlifts(client, auth_headers, seed_group):
    headers, _ = auth_headers()
    seed_group("Romanian Deadlift", ["RDL", "Stiff-Leg Deadlift"])
    seed_group("Single Leg Romanian Deadlift", ["Single Leg RDL", "SL RDL", "One Leg RDL"])

    response = client.get("/exercises?search=romanian", headers=headers)
    assert response.status_code == 200, response.text

    assert sorted(ex["name"] for ex in response.json()) == [
        "Romanian Deadlift",
        "Single Leg Romanian Deadlift",
    ]


def test_group_without_canonical_library_name_falls_back_to_longest(client, auth_headers, seed_group):
    """Groups predating EXERCISES_DATA keep the old longest-name behaviour."""
    headers, _ = auth_headers()
    seed_group("Zercher Hold", ["Zercher Carry Hold"], category="Legs", primary_muscle="Quads")

    names = _names(client, headers)

    assert "Zercher Carry Hold" in names
    assert "Zercher Hold" not in names
