"""
Static legal / support pages.

App Store Connect requires a reachable privacy-policy URL and support URL for
every submission, and ScanPaywallView links to /privacy from inside the app.
A 404 here is an App Review blocker, so the routes are pinned by tests rather
than left to manual spot-checks. See docs/app-store-launch.md.
"""
import pytest
from fastapi.testclient import TestClient

LEGAL_PATHS = ["/privacy", "/terms", "/support"]


@pytest.mark.parametrize("path", LEGAL_PATHS)
def test_legal_page_is_public_html(client: TestClient, path: str) -> None:
    """Reachable without auth — App Review and the App Store fetch these anonymously."""
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text


@pytest.mark.parametrize("path", LEGAL_PATHS)
def test_legal_page_is_mobile_readable(client: TestClient, path: str) -> None:
    """These open in an in-app browser on a phone, so the viewport tag matters."""
    text = client.get(path).text

    assert 'name="viewport"' in text
    assert "<title>" in text


def test_privacy_policy_declares_every_collected_data_type(client: TestClient) -> None:
    """
    The policy must stay in sync with PrivacyInfo.xcprivacy and the App Store
    Connect privacy label — Apple cross-checks them, and a data type collected
    but undisclosed is both a compliance problem and a submission blocker.
    """
    text = client.get("/privacy").text.lower()

    for disclosure in ("email", "workout", "bodyweight", "apple health", "photo"):
        assert disclosure in text, f"privacy policy no longer discloses {disclosure!r}"


def test_privacy_policy_documents_third_party_processors(client: TestClient) -> None:
    """Screenshots leave for Anthropic and WHOOP data is read on the user's behalf."""
    text = client.get("/privacy").text.lower()

    assert "anthropic" in text
    assert "whoop" in text


def test_privacy_policy_documents_account_deletion(client: TestClient) -> None:
    """Guideline 5.1.1(v): account deletion must exist and be described."""
    text = client.get("/privacy").text.lower()

    assert "delete" in text


def test_terms_cover_purchases_and_medical_disclaimer(client: TestClient) -> None:
    """The two clauses that matter for a paid fitness app."""
    text = client.get("/terms").text.lower()

    assert "in-app purchase" in text or "in app purchase" in text
    assert "medical" in text


def test_support_page_offers_a_contact_route(client: TestClient) -> None:
    """A support URL with no way to make contact does not satisfy the requirement."""
    text = client.get("/support").text

    assert "mailto:" in text


def test_support_page_links_privacy_and_terms(client: TestClient) -> None:
    text = client.get("/support").text

    assert 'href="/privacy"' in text
    assert 'href="/terms"' in text
