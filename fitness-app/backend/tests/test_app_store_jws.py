"""
App Store JWS verification (control-plane spec §6.5).

The verifier (``app/core/app_store_jws.py``) is exercised with JWSs built
from a throwaway ES256 chain — root → intermediate → leaf generated here
with ``cryptography`` — and the pinned Apple root is swapped by monkeypatch.
The route tests cover the request binding (transaction / product / bundle /
environment / revocation / appAccountToken) and the two-phase
``PURCHASE_REQUIRE_JWS`` rollout. One test asserts the vendored Apple Root
CA - G3 matches Apple's published SHA-256 fingerprint.
"""
import base64
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.x509.oid import NameOID

from app.core import app_store_jws as jws_mod
from app.core.app_store_jws import (
    INTERMEDIATE_WWDR_OID,
    LEAF_RECEIPT_SIGNING_OID,
    ROOT_CERT_SHA256,
    InvalidSignedTransaction,
    verify_signed_transaction,
)
from app.core.config import settings
from app.models.scan_balance import PurchaseRecord
from app.services.entitlement_service import UNLIMITED_PRODUCT_ID

SCAN_20 = "com.nickchua.fitnessapp.scan_20"
BUNDLE = "com.nickchua.fitnessapp"
NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
ROUTE = "/scan-balance/verify-purchase"


# ── throwaway chain ──────────────────────────────────────────────────────────

@dataclass
class Chain:
    root: x509.Certificate
    intermediate: x509.Certificate
    leaf: x509.Certificate
    leaf_key: ec.EllipticCurvePrivateKey


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(
    subject: str,
    issuer_name: x509.Name,
    public_key,
    signer_key,
    *,
    not_before: datetime,
    not_after: datetime,
    ca: bool,
    marker: Optional[x509.ObjectIdentifier] = None,
) -> x509.Certificate:
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(subject))
        .issuer_name(issuer_name)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if marker is not None:
        builder = builder.add_extension(x509.UnrecognizedExtension(marker, b"\x05\x00"), critical=False)
    return builder.sign(signer_key, hashes.SHA256())


def build_chain(
    *,
    leaf_marker: Optional[x509.ObjectIdentifier] = LEAF_RECEIPT_SIGNING_OID,
    intermediate_marker: Optional[x509.ObjectIdentifier] = INTERMEDIATE_WWDR_OID,
    leaf_not_before: datetime = NOW - timedelta(days=30),
    leaf_not_after: datetime = NOW + timedelta(days=365),
    intermediate_not_after: datetime = NOW + timedelta(days=1000),
    intermediate_is_ca: bool = True,
) -> Chain:
    root_key = ec.generate_private_key(ec.SECP384R1())
    inter_key = ec.generate_private_key(ec.SECP256R1())
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    root = _cert(
        "Test Root CA", _name("Test Root CA"), root_key.public_key(), root_key,
        not_before=NOW - timedelta(days=3650), not_after=NOW + timedelta(days=3650), ca=True,
    )
    intermediate = _cert(
        "Test WWDR", root.subject, inter_key.public_key(), root_key,
        not_before=NOW - timedelta(days=1000), not_after=intermediate_not_after,
        ca=intermediate_is_ca, marker=intermediate_marker,
    )
    leaf = _cert(
        "Test Receipt Signer", intermediate.subject, leaf_key.public_key(), inter_key,
        not_before=leaf_not_before, not_after=leaf_not_after, ca=False, marker=leaf_marker,
    )
    return Chain(root=root, intermediate=intermediate, leaf=leaf, leaf_key=leaf_key)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _der_b64(cert: x509.Certificate) -> str:
    return base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode("ascii")


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def payload_for(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "transactionId": "2000000900000001",
        "originalTransactionId": "2000000900000001",
        "bundleId": BUNDLE,
        "productId": SCAN_20,
        "purchaseDate": _ms(NOW - timedelta(minutes=1)),
        "signedDate": _ms(NOW),
        "environment": "Sandbox",
        "type": "Consumable",
        "inAppOwnershipType": "PURCHASED",
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def make_jws(
    chain: Chain,
    payload: Dict[str, Any],
    *,
    alg: str = "ES256",
    signer: Optional[ec.EllipticCurvePrivateKey] = None,
    x5c: Optional[list] = None,
) -> str:
    header = {"alg": alg, "x5c": x5c if x5c is not None else [_der_b64(chain.leaf), _der_b64(chain.intermediate), _der_b64(chain.root)]}
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    der = (signer or chain.leaf_key).sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return f"{signing_input}.{_b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


@pytest.fixture(scope="module")
def chain() -> Chain:
    return build_chain()


@pytest.fixture(autouse=True)
def pin_root(chain, monkeypatch):
    """Pin the module chain's root; returns a function to pin another chain's root instead."""
    def pin(c: Chain) -> None:
        monkeypatch.setattr(jws_mod, "trusted_roots", lambda: (c.root,))

    pin(chain)
    return pin


# ── the verifier ─────────────────────────────────────────────────────────────

class TestVerifier:
    def test_valid_jws_returns_payload(self, chain):
        token = make_jws(chain, payload_for(appAccountToken="7A6E0C3E-1F3B-4D2A-9C8B-2F1E5A6B7C8D"))
        tx = verify_signed_transaction(token)
        assert tx.transaction_id == "2000000900000001"
        assert tx.original_transaction_id == "2000000900000001"
        assert tx.bundle_id == BUNDLE and tx.product_id == SCAN_20
        assert tx.environment == "Sandbox"
        assert tx.signed_date == NOW and tx.purchase_date == NOW - timedelta(minutes=1)
        assert tx.revoked is False and tx.revocation_date is None
        assert tx.app_account_token == "7a6e0c3e-1f3b-4d2a-9c8b-2f1e5a6b7c8d"

    def test_revocation_date_is_surfaced(self, chain):
        tx = verify_signed_transaction(make_jws(chain, payload_for(revocationDate=_ms(NOW))))
        assert tx.revoked is True and tx.revocation_date == NOW

    @pytest.mark.parametrize("alg", ["RS256", "none", "ES384", "HS256"])
    def test_wrong_alg_rejected(self, chain, alg):
        with pytest.raises(InvalidSignedTransaction, match="alg"):
            verify_signed_transaction(make_jws(chain, payload_for(), alg=alg))

    def test_leaf_from_another_intermediate_rejected(self, chain):
        other = build_chain()
        forged = make_jws(other, payload_for(), x5c=[_der_b64(other.leaf), _der_b64(chain.intermediate), _der_b64(chain.root)])
        with pytest.raises(InvalidSignedTransaction, match="leaf is not issued"):
            verify_signed_transaction(forged)

    def test_chain_to_unpinned_root_rejected(self, chain):
        other = build_chain()  # self-consistent, but its root is not pinned
        with pytest.raises(InvalidSignedTransaction, match="pinned Apple root"):
            verify_signed_transaction(make_jws(other, payload_for()))

    def test_supplied_root_in_x5c_is_ignored(self, chain):
        """A forged chain that ships its own root must not become trusted."""
        other = build_chain()
        with pytest.raises(InvalidSignedTransaction, match="pinned Apple root"):
            verify_signed_transaction(make_jws(other, payload_for(), x5c=[_der_b64(other.leaf), _der_b64(other.intermediate), _der_b64(other.root)]))

    def test_expired_leaf_rejected(self, pin_root):
        expired = build_chain(leaf_not_before=NOW - timedelta(days=400), leaf_not_after=NOW - timedelta(days=1))
        pin_root(expired)
        with pytest.raises(InvalidSignedTransaction, match="leaf certificate was not valid"):
            verify_signed_transaction(make_jws(expired, payload_for()))
        # Apple's rule: signed while the leaf was valid → still verifies.
        tx = verify_signed_transaction(make_jws(expired, payload_for(signedDate=_ms(NOW - timedelta(days=10)))))
        assert tx.signed_date == NOW - timedelta(days=10)

    def test_expired_intermediate_rejected(self, pin_root):
        stale = build_chain(intermediate_not_after=NOW - timedelta(days=1))
        pin_root(stale)
        with pytest.raises(InvalidSignedTransaction, match="intermediate certificate was not valid"):
            verify_signed_transaction(make_jws(stale, payload_for()))

    def test_non_ca_intermediate_rejected(self, pin_root):
        """A leaf signed by an end-entity cert that the root issued must not count as a chain."""
        flat = build_chain(intermediate_is_ca=False)
        pin_root(flat)
        with pytest.raises(InvalidSignedTransaction, match="not a CA"):
            verify_signed_transaction(make_jws(flat, payload_for()))

    def test_out_of_range_timestamp_rejected_not_500(self, chain):
        with pytest.raises(InvalidSignedTransaction, match="out of range"):
            verify_signed_transaction(make_jws(chain, payload_for(signedDate=10**30)))

    def test_missing_leaf_oid_rejected(self, pin_root):
        bare = build_chain(leaf_marker=None)
        pin_root(bare)
        with pytest.raises(InvalidSignedTransaction, match="receipt-signing"):
            verify_signed_transaction(make_jws(bare, payload_for()))

    def test_missing_intermediate_oid_rejected(self, pin_root):
        bare = build_chain(intermediate_marker=None)
        pin_root(bare)
        with pytest.raises(InvalidSignedTransaction, match="WWDR"):
            verify_signed_transaction(make_jws(bare, payload_for()))

    def test_tampered_payload_rejected(self, chain):
        header, _, signature = make_jws(chain, payload_for()).split(".")
        tampered = _b64url(json.dumps(payload_for(productId=UNLIMITED_PRODUCT_ID)).encode())
        with pytest.raises(InvalidSignedTransaction, match="signature"):
            verify_signed_transaction(f"{header}.{tampered}.{signature}")

    def test_signature_from_another_key_rejected(self, chain):
        with pytest.raises(InvalidSignedTransaction, match="signature"):
            verify_signed_transaction(make_jws(chain, payload_for(), signer=ec.generate_private_key(ec.SECP256R1())))

    @pytest.mark.parametrize("bad", ["", "abc", "a.b", "a.b.c.d", "not base64!.x.y"])
    def test_malformed_tokens_rejected(self, bad):
        with pytest.raises(InvalidSignedTransaction):
            verify_signed_transaction(bad)

    def test_x5c_with_only_a_leaf_rejected(self, chain):
        with pytest.raises(InvalidSignedTransaction, match="x5c"):
            verify_signed_transaction(make_jws(chain, payload_for(), x5c=[_der_b64(chain.leaf)]))

    @pytest.mark.parametrize("missing", ["transactionId", "bundleId", "productId", "signedDate", "environment"])
    def test_missing_payload_field_rejected(self, chain, missing):
        with pytest.raises(InvalidSignedTransaction, match=missing):
            verify_signed_transaction(make_jws(chain, payload_for(**{missing: None})))


class TestPinnedRoot:
    def test_vendored_root_matches_apples_published_fingerprint(self):
        root = jws_mod._load_pinned_root()
        assert root.fingerprint(hashes.SHA256()).hex() == ROOT_CERT_SHA256
        assert root.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "Apple Root CA - G3"
        assert root.issuer == root.subject
        assert root.not_valid_after_utc > datetime.now(timezone.utc)

    def test_default_trust_anchor_is_the_vendored_root(self, monkeypatch):
        monkeypatch.undo()  # drop the autouse pin for this one test
        assert [c.fingerprint(hashes.SHA256()).hex() for c in jws_mod.trusted_roots()] == [ROOT_CERT_SHA256]


# ── the route ────────────────────────────────────────────────────────────────

def _post(client, headers, txn: str, product_id: str, signed: Optional[str]):
    body: Dict[str, Any] = {"transaction_id": txn, "product_id": product_id}
    if signed is not None:
        body["signed_transaction"] = signed
    return client.post(ROUTE, headers=headers, json=body)


def _record(db, txn: str) -> PurchaseRecord:
    return db.query(PurchaseRecord).filter(PurchaseRecord.transaction_id == txn).one()


class TestVerifyPurchaseRoute:
    def test_verified_purchase_credits_and_records_provenance(self, client, db, auth_headers, chain):
        headers, user = auth_headers(email="jws-ok@example.com")
        txn = "2000000900000101"
        token = make_jws(chain, payload_for(transactionId=txn, originalTransactionId=txn, appAccountToken=user.id.upper()))
        response = _post(client, headers, txn, SCAN_20, token)
        assert response.status_code == 200, response.text
        assert response.json()["credits_added"] == 20
        row = _record(db, txn)
        assert row.verified is True and row.environment == "Sandbox"
        assert row.original_transaction_id == txn
        assert row.purchase_date.replace(tzinfo=timezone.utc) == NOW - timedelta(minutes=1)

    def test_absent_jws_accepted_unverified_in_phase_1(self, client, db, auth_headers, monkeypatch):
        monkeypatch.setattr(settings, "PURCHASE_REQUIRE_JWS", False)
        headers, _ = auth_headers(email="jws-absent@example.com")
        response = _post(client, headers, "2000000900000102", SCAN_20, None)
        assert response.status_code == 200, response.text
        row = _record(db, "2000000900000102")
        assert row.verified is False and row.environment is None and row.purchase_date is None

    def test_absent_jws_422_in_phase_2(self, client, db, auth_headers, monkeypatch):
        monkeypatch.setattr(settings, "PURCHASE_REQUIRE_JWS", True)
        headers, _ = auth_headers(email="jws-required@example.com")
        response = _post(client, headers, "2000000900000103", SCAN_20, None)
        assert response.status_code == 422
        assert response.json()["detail"] == "signed_transaction required"
        assert db.query(PurchaseRecord).filter(PurchaseRecord.transaction_id == "2000000900000103").count() == 0

    def test_valid_jws_still_verified_in_phase_2(self, client, db, auth_headers, chain, monkeypatch):
        monkeypatch.setattr(settings, "PURCHASE_REQUIRE_JWS", True)
        headers, _ = auth_headers(email="jws-required-ok@example.com")
        txn = "2000000900000104"
        assert _post(client, headers, txn, SCAN_20, make_jws(chain, payload_for(transactionId=txn))).status_code == 200
        assert _record(db, txn).verified is True

    @pytest.mark.parametrize(
        "overrides",
        [
            {"transactionId": "2000000900000999"},
            {"productId": UNLIMITED_PRODUCT_ID},
            {"bundleId": "com.example.other"},
            {"revocationDate": _ms(NOW)},
            {"appAccountToken": str(uuid.uuid4())},
        ],
        ids=["transaction", "product", "bundle", "revoked", "appAccountToken"],
    )
    def test_binding_mismatch_422_with_one_detail(self, client, db, auth_headers, chain, overrides, caplog):
        headers, user = auth_headers(email=f"jws-{list(overrides)[0].lower()}@example.com")
        txn = "2000000900000105"
        token = make_jws(chain, payload_for(**{"transactionId": txn, **overrides}))
        with caplog.at_level("WARNING", logger="app.api.scan_balance"):
            response = _post(client, headers, txn, SCAN_20, token)
        assert response.status_code == 422
        assert response.json()["detail"] == "signed_transaction could not be verified for this purchase"
        assert db.query(PurchaseRecord).filter(PurchaseRecord.transaction_id == txn).count() == 0
        # Reason + transaction id are logged; the JWS never is.
        assert txn in caplog.text and token not in caplog.text
        assert user.id not in caplog.text

    def test_bad_signature_422_and_jws_never_logged(self, client, auth_headers, chain, caplog):
        headers, _ = auth_headers(email="jws-forged@example.com")
        txn = "2000000900000106"
        token = make_jws(chain, payload_for(transactionId=txn), signer=ec.generate_private_key(ec.SECP256R1()))
        with caplog.at_level("WARNING", logger="app.api.scan_balance"):
            response = _post(client, headers, txn, SCAN_20, token)
        assert response.status_code == 422
        assert "signature" in caplog.text and token not in caplog.text

    def test_sandbox_rejected_when_only_production_allowed(self, client, auth_headers, chain, monkeypatch):
        monkeypatch.setattr(settings, "PURCHASE_ALLOWED_ENVIRONMENTS", "Production")
        headers, _ = auth_headers(email="jws-env@example.com")
        txn = "2000000900000107"
        assert _post(client, headers, txn, SCAN_20, make_jws(chain, payload_for(transactionId=txn, environment="Sandbox"))).status_code == 422
        assert _post(client, headers, txn, SCAN_20, make_jws(chain, payload_for(transactionId=txn, environment="Production"))).status_code == 200

    def test_unknown_environment_rejected_by_the_route(self, client, auth_headers, chain):
        """The allow-list is the only owner of the environment policy (default Production,Sandbox)."""
        headers, _ = auth_headers(email="jws-env-xcode@example.com")
        txn = "2000000900000115"
        assert _post(client, headers, txn, SCAN_20, make_jws(chain, payload_for(transactionId=txn, environment="Xcode"))).status_code == 422

    def test_bundle_id_comes_from_settings(self, client, auth_headers, chain, monkeypatch):
        monkeypatch.setattr(settings, "APP_STORE_BUNDLE_ID", "com.example.renamed")
        headers, _ = auth_headers(email="jws-bundle-setting@example.com")
        txn = "2000000900000108"
        assert _post(client, headers, txn, SCAN_20, make_jws(chain, payload_for(transactionId=txn))).status_code == 422
        assert _post(client, headers, txn, SCAN_20, make_jws(chain, payload_for(transactionId=txn, bundleId="com.example.renamed"))).status_code == 200

    def test_duplicate_transaction_stays_idempotent_even_with_a_bad_jws(self, client, auth_headers, chain):
        headers, _ = auth_headers(email="jws-dup@example.com")
        txn = "2000000900000109"
        first = _post(client, headers, txn, SCAN_20, make_jws(chain, payload_for(transactionId=txn)))
        assert first.status_code == 200
        second = _post(client, headers, txn, SCAN_20, "garbage.jws.value")
        assert second.status_code == 200
        assert second.json()["credits_added"] == 0
        assert second.json()["new_balance"] == first.json()["new_balance"]

    def test_verified_unlimited_alert_names_the_environment(self, client, auth_headers, chain, captured_owner_alerts):
        headers, _ = auth_headers(email="jws-alert@example.com")
        txn = "2000000900000110"
        token = make_jws(chain, payload_for(transactionId=txn, productId=UNLIMITED_PRODUCT_ID, type="Non-Consumable", environment="Production"))
        assert _post(client, headers, txn, UNLIMITED_PRODUCT_ID, token).status_code == 200
        assert len(captured_owner_alerts) == 1
        assert "verified (Production)" in captured_owner_alerts[0] and token not in captured_owner_alerts[0]

    def test_unverified_unlimited_alert_says_client_claim(self, client, auth_headers, captured_owner_alerts):
        headers, _ = auth_headers(email="jws-alert-claim@example.com")
        assert _post(client, headers, "2000000900000111", UNLIMITED_PRODUCT_ID, None).status_code == 200
        assert len(captured_owner_alerts) == 1 and "unverified client claim" in captured_owner_alerts[0]

    def test_caps_still_apply_to_verified_purchases(self, client, auth_headers, chain, monkeypatch):
        """§6.5: the interim caps are kept even when the receipt verifies."""
        monkeypatch.setattr(settings, "PURCHASE_MAX_VERIFICATIONS_PER_DAY", 1)
        headers, _ = auth_headers(email="jws-caps@example.com")
        for txn, expected in (("2000000900000112", 200), ("2000000900000113", 429)):
            response = _post(client, headers, txn, SCAN_20, make_jws(chain, payload_for(transactionId=txn)))
            assert response.status_code == expected, response.text

    def test_jws_checked_before_the_product_lookup(self, client, auth_headers, chain):
        """A bad JWS is 422 even for an unknown product (ordering: duplicate → id → JWS → product)."""
        headers, _ = auth_headers(email="jws-order@example.com")
        txn = "2000000900000114"
        response = _post(client, headers, txn, "com.bogus.product", make_jws(chain, payload_for(transactionId=txn, productId="com.bogus.product"), signer=ec.generate_private_key(ec.SECP256R1())))
        assert response.status_code == 422
