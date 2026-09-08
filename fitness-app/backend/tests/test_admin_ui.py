"""
The owner console's static shell (control-plane spec §10.1, §16 ``test_admin_ui``).

The page is three files on one ``StaticFiles`` mount at ``/admin/ui/`` — no
build step, no server-side interpolation, no inline handlers or styles
(the CSP has no ``'unsafe-inline'``), and the token never touches storage.
The tests here read the shipped files the way a reviewer would, plus the
header contract on the page and on the JSON it calls.
"""
import re
import uuid
from pathlib import Path

import pytest
from starlette.routing import Mount

from app.core.admin_headers import ADMIN_CSP, ADMIN_RESPONSE_HEADERS
from main import ADMIN_UI_DIR, app

INDEX = ADMIN_UI_DIR / "index.html"
JS = ADMIN_UI_DIR / "admin.js"
CSS = ADMIN_UI_DIR / "admin.css"
SECURITY_HEADERS = {name.lower(): value for name, value in ADMIN_RESPONSE_HEADERS.items()}  # the middleware's own contract


def _assert_admin_headers(response) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert response.headers.get(name) == value, (name, response.headers.get(name))


class TestStaticMount:
    def test_files_exist_and_are_the_only_console_assets(self):
        served = {p.name for p in ADMIN_UI_DIR.iterdir() if p.suffix in {".html", ".js", ".css"}}
        assert served == {"index.html", "admin.js", "admin.css"}
        assert not list(ADMIN_UI_DIR.glob("*.py")), "the static dir must hold no Python"  # nothing to import, nothing to interpolate

    @pytest.mark.parametrize(
        "path, content_type, source",
        [("/admin/ui/", "text/html", INDEX), ("/admin/ui/admin.js", "text/javascript", JS), ("/admin/ui/admin.css", "text/css", CSS)],
    )
    def test_files_are_served_verbatim_with_their_types_and_the_headers(self, client, path, content_type, source):
        response = client.get(path)  # no token: the shell is the one public /admin path besides /admin/session
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(content_type)
        _assert_admin_headers(response)
        assert response.text == source.read_text(encoding="utf-8")  # zero server-side interpolation

    def test_bare_mount_path_redirects_to_the_page(self, client):
        response = client.get("/admin/ui", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"].endswith("/admin/ui/")

    @pytest.mark.parametrize("path", ["/admin/ui/nope.html", "/admin/ui/../main.py", "/admin/ui/%2e%2e/main.py"])
    def test_unknown_and_traversal_paths_are_404(self, client, path):
        response = client.get(path)
        assert response.status_code == 404
        _assert_admin_headers(response)

    def test_exactly_one_static_mount(self):
        """A Mount never reaches OpenAPI; the /admin route-enumeration gate lives in test_admin_users."""
        mounts = [r for r in app.routes if getattr(r, "path", "") == "/admin/ui"]
        assert len(mounts) == 1 and isinstance(mounts[0], Mount)

    def test_csp_has_no_unsafe_inline(self):
        assert "default-src 'self'" in ADMIN_CSP
        assert "script-src 'self'" in ADMIN_CSP
        assert "unsafe-inline" not in ADMIN_CSP
        assert "unsafe-eval" not in ADMIN_CSP


class TestJsonHeaders:
    def test_users_json_is_no_store(self, client, admin_headers):
        headers, _ = admin_headers()
        response = client.get("/admin/users", headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        _assert_admin_headers(response)

    def test_unauthenticated_json_is_401_and_still_no_store(self, client):
        response = client.get("/admin/users")
        assert response.status_code == 401
        _assert_admin_headers(response)


class TestShellSource:
    """Static review of the shipped files — what the CSP relies on."""

    def test_no_inline_event_handlers(self):
        pattern = re.compile(r"\son[a-z]+\s*=\s*[\"']", re.IGNORECASE)  # onclick="…" in markup or in a JS template
        for path in (INDEX, JS):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                assert not pattern.search(line), f"{path.name}:{lineno}: inline handler: {line.strip()}"

    def test_no_inline_script_or_style_in_the_page(self):
        html = INDEX.read_text(encoding="utf-8")
        for match in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.DOTALL | re.IGNORECASE):
            assert "src=" in match.group(1) and not match.group(2).strip(), "inline <script> body"
        assert not re.search(r"<style\b", html, re.IGNORECASE)
        assert not re.search(r"\sstyle\s*=", html, re.IGNORECASE)

    def test_page_only_references_same_origin_assets(self):
        html = INDEX.read_text(encoding="utf-8")
        refs = re.findall(r"(?:src|href)\s*=\s*\"([^\"]+)\"", html)
        assert refs and all(ref.startswith("./") for ref in refs), refs
        assert {Path(ref).name for ref in refs} == {"admin.js", "admin.css"}

    def test_js_never_persists_the_token_or_sets_inline_styles(self):
        js = JS.read_text(encoding="utf-8")
        for forbidden in ("localStorage", "sessionStorage", "document.cookie", "indexedDB", "eval(", "new Function("):
            assert forbidden not in js, forbidden
        assert not re.search(r"\.setAttribute\(\s*['\"]style['\"]", js)
        assert not re.search(r"\sstyle=\\?[\"']", js), "inline style attribute in a template"
        assert "window.location.origin" in js

    def test_js_carries_the_contract_details_the_api_enforces(self):
        js = JS.read_text(encoding="utf-8")
        assert "'Idempotency-Key'" in js  # credits (spec §7.1)
        assert "confirm_email" in js  # purge (spec §8.2)
        assert "/admin/session" in js and "/admin/me" in js
        assert "closest('[data-action]')" in js  # delegated clicks, the mobile rule

    def test_css_declares_the_desktop_and_phone_lanes(self):
        css = CSS.read_text(encoding="utf-8")
        assert "--rail-w: 220px" in css and "--drawer-w: 420px" in css
        assert "@media (max-width: 767px)" in css
        assert "touch-action: manipulation" in css
        assert "min-height: 44px" in css


class TestSortOrder:
    """``sort`` / ``order`` on ``GET /admin/users`` — the table headers depend on them.

    ``email`` / ``credits`` / ``last_active`` ordering and paging are covered by
    ``test_admin_users``; this adds the ``created`` sort the Created header uses,
    the default direction, and the rejection of an unknown ``order``.
    """

    def _emails(self, client, headers, **params):
        response = client.get("/admin/users", headers=headers, params=params)
        assert response.status_code == 200, response.text
        return [row["email"] for row in response.json()["items"]]

    def test_created_sort_and_default_order(self, client, admin_headers, create_test_user):
        tag = uuid.uuid4().hex[:8]
        headers, _ = admin_headers(email=f"{tag}-admin@example.com")
        first = create_test_user(email=f"{tag}-first@example.com")[0]
        second = create_test_user(email=f"{tag}-second@example.com")[0]
        asc = self._emails(client, headers, q=tag, sort="created", order="asc")
        assert asc.index(first.email) < asc.index(second.email)
        desc = self._emails(client, headers, q=tag, sort="created")  # order defaults to desc
        assert desc.index(second.email) < desc.index(first.email)

    @pytest.mark.parametrize("params", [{"sort": "password_hash"}, {"order": "sideways"}])
    def test_unknown_sort_or_order_is_422(self, client, admin_headers, params):
        headers, _ = admin_headers()
        assert client.get("/admin/users", headers=headers, params=params).status_code == 422
