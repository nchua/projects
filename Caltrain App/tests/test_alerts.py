"""Service-alert parsing: real 511 PascalCase payload + GTFS-spec snake_case."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.departures import parse_alerts

# The real fixture's Header.Timestamp — alerts in it are active at this moment.
CAPTURE_NOW = datetime.fromtimestamp(1782969673, tz=timezone.utc)


def test_real_fixture_parses_pascalcase(servicealerts_payload):
    alerts = parse_alerts(servicealerts_payload, now=CAPTURE_NOW)
    assert len(alerts) >= 2
    for alert in alerts:
        assert alert["id"]
        assert alert["header"]
    headers = " ".join(a["header"] for a in alerts)
    assert "World Cup" in headers or "Millbrae" in headers


def test_prefers_english_translation(servicealerts_payload):
    alerts = parse_alerts(servicealerts_payload, now=CAPTURE_NOW)
    millbrae = [a for a in alerts if "Millbrae" in a["header"]]
    assert millbrae
    assert "Accessibility" in millbrae[0]["header"]  # en, not es/zh/vi


def test_snake_case_gtfs_spec_keys_also_parse():
    now = datetime.now(timezone.utc)
    payload = {
        "entity": [
            {
                "id": "x1",
                "alert": {
                    "active_period": [{"start": int((now - timedelta(hours=1)).timestamp())}],
                    "header_text": {"translation": [{"text": "Snake alert", "language": "en"}]},
                    "description_text": {"translation": [{"text": "Details", "language": "en"}]},
                },
            }
        ]
    }
    alerts = parse_alerts(payload, now=now)
    assert alerts == [
        {
            "id": "x1",
            "header": "Snake alert",
            "description": "Details",
            "active_period": {"start": alerts[0]["active_period"]["start"], "end": None},
        }
    ]


def test_expired_alerts_filtered():
    now = datetime.now(timezone.utc)
    payload = {
        "Entities": [
            {
                "Id": "old",
                "Alert": {
                    "ActivePeriods": [
                        {
                            "Start": int((now - timedelta(days=10)).timestamp()),
                            "End": int((now - timedelta(days=1)).timestamp()),
                        }
                    ],
                    "HeaderText": {"Translations": [{"Text": "Over", "Language": "en"}]},
                },
            }
        ]
    }
    assert parse_alerts(payload, now=now) == []


def test_alert_without_text_is_skipped():
    payload = {"Entities": [{"Id": "empty", "Alert": {"ActivePeriods": []}}]}
    assert parse_alerts(payload) == []
