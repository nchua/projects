"""
The owner console's static shell (control-plane spec §10.1, §16 ``test_admin_ui``).

The page is three files on one ``StaticFiles`` mount at ``/admin/ui/`` — no
build step, no server-side interpolation, no inline handlers or styles
(the CSP has no ``'unsafe-inline'``), and the token never touches storage.
The tests here read the shipped files the way a reviewer would, plus the
header contract on the page and on the JSON it calls.
"""
import re
import shutil
import subprocess
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
        for forbidden in ("sessionStorage", "document.cookie", "indexedDB", "eval(", "new Function("):
            assert forbidden not in js, forbidden
        # localStorage exists for saved views (console v2 §4.3) and the Diagnostics open/closed bit (§4.4) only:
        # every use names VIEWS_KEY or DIAG_KEY and none mentions the token
        storage_lines = [line for line in js.splitlines() if "localStorage" in line]
        assert storage_lines, "saved views live in localStorage"
        assert any("VIEWS_KEY" in line for line in storage_lines) and any("DIAG_KEY" in line for line in storage_lines)
        for line in storage_lines:
            assert ("VIEWS_KEY" in line or "DIAG_KEY" in line) and "token" not in line, line.strip()
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


class TestConsoleV2Shell:
    """Console v2 §4.1 / §4.3 / §7.2: the default route, the nav order, and the hash-state pair."""

    def test_default_route_is_hunters(self):
        js = JS.read_text(encoding="utf-8")
        assert "segs[0] || 'hunters'" in js  # `#/` → Hunters (spec §4.1)
        assert "location.hash = '#/hunters'" in js  # an unknown screen lands on Hunters too

    def test_nav_order_by_job_frequency(self):
        html = INDEX.read_text(encoding="utf-8")
        rail = re.search(r'<nav class="rnav".*?</nav>', html, re.DOTALL).group(0)
        assert re.findall(r'data-nav="([a-z]+)"', rail) == ["hunters", "overview", "audit", "settings", "catalog"]
        tabs = re.search(r'<nav class="tabbar".*?</nav>', html, re.DOTALL).group(0)
        assert re.findall(r'data-nav="([a-z]+)"', tabs) == ["hunters", "overview", "audit"]  # the phone lane (spec §4.1)

    def test_js_carries_the_v2_contract_details(self):
        js = JS.read_text(encoding="utf-8")
        for needle in ("'/plan'", "/admin/users/plan", "/admin/users/state", "/admin/users/purge", "confirm_count", "remove_unlimited", "user.plan_change"):
            assert needle in js, needle
        assert re.search(r"userPath\(rows\[0\]\.id, '/plan'\), body, \{ 'Idempotency-Key': dr\.idem \}", js)  # single Change plan is idempotent (§7.4 v2.1)

    def test_js_carries_the_w6_contract_details(self):
        """Console v2 §4.4–§4.7 + §5.5: the detail, the settings drawer and the phone lane read what the API ships."""
        js = JS.read_text(encoding="utf-8")
        # Settings (§4.5, §5.5): PATCH /admin/settings/{key}, null resets, step-up follows row.tier, the live warning line
        assert "function editSettingSpec(row)" in js
        assert re.search(r"api\('PATCH', '/admin/settings/' \+ encodeURIComponent\(row\.key\)", js)
        assert "value: v.mode === 'reset' ? null : settingParse(row, v)" in js
        assert "password: destructive" in js and "row.tier === 'destructive'" in js
        assert "row.warning" in js and "RESET TO DEFAULT" in js
        assert "auditLookup: { action: 'settings.update' }" in js
        for needle in ("r.items", "r.env", "whoop_configured", "git_sha", "token_ttl_minutes"):  # the v2.3 settings response
            assert needle in js, needle
        # Detail (§4.4): the four cards read the detail blocks; Diagnostics is a <details> remembered under DIAG_KEY
        for needle in ("c-plan", "c-scans", "c-account", "c-purchases", "c-diag", "c-activity", "d.plan", "d.account", "d.scans", "d.activity", "pl.last_change", "acc.purge_at", "sc.used_7d", "sc.today_count"):
            assert needle in js, needle
        assert 'id="diag"' in js and "var DIAG_KEY = " in js
        # Audit / Catalog (§4.6) and the bulk request id (v2.3)
        for needle in ("'request_id'", "'X-Request-ID': rid", "audit-mine", "p.sold_verified", "by_plan_source", "scans_4wk_by_plan", "purchased_credits_total", "'session_count'"):
            assert needle in js, needle

    def test_css_orders_the_phone_detail_lane(self):
        css = CSS.read_text(encoding="utf-8")
        phone = css[css.index("@media (max-width: 767px)"):]
        orders = dict(re.findall(r"\.(c-[a-z]+) \{ order: (\d+); \}", phone))
        assert [k for k, _ in sorted(orders.items(), key=lambda kv: int(kv[1]))] == ["c-plan", "c-scans", "c-account", "c-purchases", "c-diag", "c-activity"]  # §4.7
        assert ".drawer .field, .drawer .radios label" in phone and "min-height: 44px" in phone  # §5.7 sheet targets

    @staticmethod
    def _hash_state_block() -> str:
        js = JS.read_text(encoding="utf-8")
        start = js.index("// ── hunters hash state")
        end = js.index("// ── end hunters hash state")
        return js[start:end]

    def test_hash_state_pair_is_pure(self):
        block = self._hash_state_block()
        for forbidden in ("document", "window", "location", "api(", "state.", "$("):
            assert forbidden not in block, forbidden

    def test_filter_state_round_trips_through_the_hash(self, tmp_path):
        node = shutil.which("node")
        if not node:
            pytest.skip("node is not installed here; the hash-state pair runs in the browser")
        harness = self._hash_state_block() + """
const assert = require('assert');
const rt = s => parseHuntersState(serializeHuntersState(parseHuntersState(s)));
// the default view is the empty hash
assert.deepStrictEqual(parseHuntersState(''), { q: '', status: ['active', 'inactive'], plan: [], joined: null, sort: 'last_active', order: 'desc', offset: 0 });
assert.strictEqual(serializeHuntersState(parseHuntersState('')), '');
assert.strictEqual(serializeHuntersState(parseHuntersState('?status=active,inactive&sort=last_active&order=desc')), '');
// every filter survives a round trip, and the serialized form is stable
for (const s of ['?status=purge_eligible', '?status=deleted,purge_eligible&plan=free&q=nick&sort=plan&order=asc&joined_days=30&offset=50', '?plan=credits,unlimited', '?joined_days=7', '?sort=scans_4wk&order=desc', '?q=a%20b']) {
  assert.deepStrictEqual(rt(s), parseHuntersState(s), s);
  assert.strictEqual(serializeHuntersState(rt(s)), serializeHuntersState(parseHuntersState(s)), s);
}
// tokens are normalized: order by the allow-list, duplicates dropped, unknown values ignored, "all plans" collapses to the default
assert.deepStrictEqual(parseHuntersState('?status=inactive,active,active,bogus').status, ['active', 'inactive']);
assert.strictEqual(serializeHuntersState(parseHuntersState('?plan=free,credits,unlimited,override')), '');
assert.strictEqual(parseHuntersState('?sort=password_hash&order=sideways&joined_days=12&offset=-3').sort, 'last_active');
assert.deepStrictEqual(parseHuntersState('?joined_days=12&offset=-3'), Object.assign(parseHuntersState(''), {}));
// the csv stays readable in the address bar, and a full hash is accepted as input
assert.strictEqual(serializeHuntersState(parseHuntersState('?status=deleted,purge_eligible')), '?status=deleted,purge_eligible');
assert.strictEqual(serializeHuntersState(parseHuntersState('#/hunters?plan=unlimited&sort=created')), '?plan=unlimited&sort=created_at');
// the v1 links Overview used to emit still land on the right view
assert.deepStrictEqual(parseHuntersState('?deleted=true').status, ['deleted', 'purge_eligible']);
assert.deepStrictEqual(parseHuntersState('?unlimited=true').plan, ['unlimited']);
console.log('ok');
"""
        script = tmp_path / "hash_state.js"
        script.write_text(harness, encoding="utf-8")
        result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ok"


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
