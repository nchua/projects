"""API tests: identity, voting budget, schedule mutations, token guard."""
from app.core.config import settings


def claim(client, name: str) -> dict:
    response = client.post("/api/members", json={"name": name})
    assert response.status_code == 200
    return response.json()["member"]


def add_idea(client, member, title="Waimea Bay", kind="activity", region="NS") -> dict:
    response = client.post(
        "/api/ideas",
        json={"title": title, "kind": kind, "region_id": region},
        headers={"X-Member-Id": member["id"]},
    )
    assert response.status_code == 200
    return response.json()["idea"]


def add_day(client) -> dict:
    response = client.post("/api/days", json={})
    assert response.status_code == 200
    return response.json()["day"]


def test_member_claim_is_idempotent_case_insensitive(client, seeded):
    first = claim(client, "Nick")
    second = claim(client, "nick")
    assert first["id"] == second["id"]


def test_vote_requires_member(client, seeded):
    member = claim(client, "Nick")
    idea = add_idea(client, member)
    response = client.put(f"/api/ideas/{idea['id']}/vote", json={"value": "interested"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "member_required"


def test_must_go_budget_enforced_per_board(client, seeded):
    member = claim(client, "Nick")
    headers = {"X-Member-Id": member["id"]}
    ideas = [add_idea(client, member, title=f"Activity {i}") for i in range(4)]
    restaurant = add_idea(client, member, title="Helena's", kind="restaurant")

    for idea in ideas[:3]:
        response = client.put(
            f"/api/ideas/{idea['id']}/vote", json={"value": "must_go"}, headers=headers
        )
        assert response.status_code == 200

    # 4th star on the same board -> 409 with the current stars listed
    response = client.put(
        f"/api/ideas/{ideas[3]['id']}/vote", json={"value": "must_go"}, headers=headers
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "must_go_budget_exceeded"
    assert sorted(error["current_must_go_idea_ids"]) == sorted(
        idea["id"] for idea in ideas[:3]
    )

    # Re-PUT on an already-starred idea is not a new star
    response = client.put(
        f"/api/ideas/{ideas[0]['id']}/vote", json={"value": "must_go"}, headers=headers
    )
    assert response.status_code == 200

    # The other board (restaurants) has its own budget
    response = client.put(
        f"/api/ideas/{restaurant['id']}/vote", json={"value": "must_go"}, headers=headers
    )
    assert response.status_code == 200

    # Score: 3 per must-go
    assert response.json()["idea"]["score"] == 3


def test_reorder_is_atomic_and_validates_ids(client, seeded):
    member = claim(client, "Nick")
    day = add_day(client)
    idea_a = add_idea(client, member, title="A")
    idea_b = add_idea(client, member, title="B")
    for idea in (idea_a, idea_b):
        response = client.post(
            f"/api/days/{day['id']}/items", json={"idea_id": idea["id"]}
        )
        assert response.status_code == 200
    items = response.json()["day"]["items"]
    ids = [item["id"] for item in items]

    stale = client.put(
        f"/api/days/{day['id']}/order", json={"item_ids": ids[:1] + ["bogus"]}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_order"

    reordered = client.put(
        f"/api/days/{day['id']}/order", json={"item_ids": list(reversed(ids))}
    )
    assert reordered.status_code == 200
    new_items = reordered.json()["day"]["items"]
    assert [item["id"] for item in new_items] == list(reversed(ids))


def test_bulk_add_orders_by_tour_order(client, seeded):
    member = claim(client, "Nick")
    day = add_day(client)
    ns_idea = add_idea(client, member, title="Waimea", region="NS")  # tour 4
    east_idea = add_idea(client, member, title="Hanauma", region="EAST")  # tour 7
    response = client.post(
        f"/api/days/{day['id']}/items/bulk",
        json={"idea_ids": [east_idea["id"], ns_idea["id"]]},
    )
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()["day"]["items"]]
    assert titles == ["Waimea", "Hanauma"]


def test_item_requires_idea_xor_free_text(client, seeded):
    day = add_day(client)
    response = client.post(f"/api/days/{day['id']}/items", json={})
    assert response.status_code == 400


def test_day_timeline_computed_in_response(client, seeded):
    member = claim(client, "Nick")
    day = add_day(client)
    idea = add_idea(client, member, title="Waimea Bay", region="NS")
    response = client.post(f"/api/days/{day['id']}/items", json={"idea_id": idea["id"]})
    payload = response.json()["day"]
    item = payload["items"][0]
    assert item["drive_minutes"] == 70  # 60 matrix + 10 buffer
    assert item["start"] == "09:40"
    assert payload["return_leg"]["drive_minutes"] == 70
    assert payload["total_drive_minutes"] == 140


def test_bootstrap_shape(client, seeded):
    claim(client, "Nick")
    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    payload = response.json()
    for key in ("version", "members", "regions", "drive_times", "days", "ideas"):
        assert key in payload


def test_trip_token_guard(client, seeded, monkeypatch):
    monkeypatch.setattr(settings, "LINK_TOKEN", "sekret")
    assert client.get("/api/health").status_code == 200
    denied = client.get("/api/version")
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "bad_token"
    allowed = client.get("/api/version", headers={"X-Trip-Token": "sekret"})
    assert allowed.status_code == 200
