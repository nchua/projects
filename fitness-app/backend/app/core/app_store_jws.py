"""
StoreKit 2 signed-transaction (JWS) verification — control-plane spec §6.5.

``verify_signed_transaction`` takes the compact JWS StoreKit hands the app as
``VerificationResult.jwsRepresentation`` and returns the signed payload as a
:class:`SignedTransaction`, or raises :class:`InvalidSignedTransaction`.

What is checked, in order:

1. compact JWS shape and a protected header with ``alg == "ES256"``;
2. an ``x5c`` chain of at least two DER certificates (leaf, intermediate; the
   third one Apple includes is its root, which is *ignored* in favour of the
   pinned copy);
3. leaf → intermediate → pinned **Apple Root CA - G3** issuance, each link
   verified with the issuer's key (``verify_directly_issued_by``), and the
   intermediate marked ``BasicConstraints CA=TRUE``;
4. Apple's marker extensions: the leaf carries the App Store receipt-signing
   OID ``1.2.840.113635.100.6.11.1`` and the intermediate the WWDR OID
   ``1.2.840.113635.100.6.2.1`` — the same pair Apple's own
   ``app-store-server-library`` requires;
5. the ES256 signature over ``header.payload`` with the leaf's P-256 key;
6. leaf and intermediate validity windows at the payload's ``signedDate``
   (Apple's rule: a transaction signed while the leaf was valid stays valid
   after that leaf expires).

Hand-rolled on ``cryptography`` instead of Apple's library: the library needs
the App Store Connect app id for Production, one verifier per environment,
and pulls ``requests`` / ``PyJWT`` for a check this module does in ~150
lines. python-jose (already a dependency) could do the ES256 step but not
the x5c chain, so the compact-JWS parse stays here too — one failure type,
one place. No online revocation (OCSP) check — the pinned root plus the
marker OIDs is the trust anchor; Apple's library makes OCSP optional too.
Which environments a purchase may come from is policy and lives in the
route (``PURCHASE_ALLOWED_ENVIRONMENTS``), not here.

Never log the JWS itself: a caller logs the reason and the transaction id.
"""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

ROOT_CERT_PATH = Path(__file__).resolve().parent / "certs" / "AppleRootCA-G3.pem"
# Published by Apple at https://www.apple.com/certificateauthority/ (SHA-256 of the DER).
ROOT_CERT_SHA256 = "63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179"

LEAF_RECEIPT_SIGNING_OID = x509.ObjectIdentifier("1.2.840.113635.100.6.11.1")
INTERMEDIATE_WWDR_OID = x509.ObjectIdentifier("1.2.840.113635.100.6.2.1")


class InvalidSignedTransaction(Exception):
    """The JWS did not verify. ``reason`` is safe to log; it never carries the token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SignedTransaction:
    """The verified JWS payload (the subset of ``JWSTransactionDecodedPayload`` we act on)."""

    transaction_id: str
    original_transaction_id: str
    bundle_id: str
    product_id: str
    purchase_date: datetime
    signed_date: datetime
    environment: str  # "Production" | "Sandbox" (StoreKit also has "Xcode")
    revocation_date: Optional[datetime] = None
    app_account_token: Optional[str] = None

    @property
    def revoked(self) -> bool:
        return self.revocation_date is not None


# ── trust anchor ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_pinned_root() -> x509.Certificate:
    return x509.load_pem_x509_certificate(ROOT_CERT_PATH.read_bytes())


def trusted_roots() -> Tuple[x509.Certificate, ...]:
    """The pinned root(s). Tests monkeypatch this to a throwaway chain."""
    return (_load_pinned_root(),)


# ── helpers ──────────────────────────────────────────────────────────────────

def _b64url_decode(segment: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (binascii.Error, ValueError) as exc:
        raise InvalidSignedTransaction("malformed base64url segment") from exc


def _json_object(raw: bytes, what: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise InvalidSignedTransaction(f"{what} is not JSON") from exc
    if not isinstance(parsed, dict):
        raise InvalidSignedTransaction(f"{what} is not a JSON object")
    return parsed


def _certificates(header: Dict[str, Any]) -> List[x509.Certificate]:
    x5c = header.get("x5c")
    if not isinstance(x5c, list) or len(x5c) < 2 or not all(isinstance(c, str) for c in x5c):
        raise InvalidSignedTransaction("x5c must list at least leaf and intermediate")
    certs: List[x509.Certificate] = []
    for encoded in x5c:
        try:
            certs.append(x509.load_der_x509_certificate(base64.b64decode(encoded, validate=True)))
        except (binascii.Error, ValueError) as exc:
            raise InvalidSignedTransaction("x5c certificate is not valid DER") from exc
    return certs


def _has_extension(cert: x509.Certificate, oid: x509.ObjectIdentifier) -> bool:
    try:
        cert.extensions.get_extension_for_oid(oid)
    except x509.ExtensionNotFound:
        return False
    return True


def _issued_by(subject: x509.Certificate, issuer: x509.Certificate, link: str) -> None:
    try:
        subject.verify_directly_issued_by(issuer)
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise InvalidSignedTransaction(f"{link} is not issued by its parent") from exc


def _is_ca(cert: x509.Certificate) -> bool:
    try:
        return bool(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
    except x509.ExtensionNotFound:
        return False


def _verify_chain(leaf: x509.Certificate, intermediate: x509.Certificate) -> None:
    if not _is_ca(intermediate):
        raise InvalidSignedTransaction("intermediate is not a CA certificate")
    _issued_by(leaf, intermediate, "leaf")
    for root in trusted_roots():
        try:
            intermediate.verify_directly_issued_by(root)
        except (InvalidSignature, ValueError, TypeError):
            continue
        return
    raise InvalidSignedTransaction("intermediate does not chain to the pinned Apple root")


def _verify_signature(leaf: x509.Certificate, signing_input: bytes, signature: bytes) -> None:
    key = leaf.public_key()
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise InvalidSignedTransaction("leaf key is not P-256")
    if len(signature) != 64:
        raise InvalidSignedTransaction("signature is not a raw ES256 (r||s) value")
    r, s = int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
    try:
        key.verify(encode_dss_signature(r, s), signing_input, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise InvalidSignedTransaction("signature does not verify") from exc


def _valid_at(cert: x509.Certificate, moment: datetime, what: str) -> None:
    if not (cert.not_valid_before_utc <= moment <= cert.not_valid_after_utc):
        raise InvalidSignedTransaction(f"{what} certificate was not valid at signedDate")


def _ms_to_datetime(payload: Dict[str, Any], field: str, *, required: bool) -> Optional[datetime]:
    value = payload.get(field)
    if value is None:
        if required:
            raise InvalidSignedTransaction(f"payload is missing {field}")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidSignedTransaction(f"payload {field} is not a timestamp")
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise InvalidSignedTransaction(f"payload {field} is out of range") from exc


def _required_str(payload: Dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (str, int)) or str(value) == "":
        raise InvalidSignedTransaction(f"payload is missing {field}")
    return str(value)


def _payload(raw: Dict[str, Any]) -> SignedTransaction:
    token = raw.get("appAccountToken")
    if token is not None and not isinstance(token, str):
        raise InvalidSignedTransaction("payload appAccountToken is invalid")
    return SignedTransaction(
        transaction_id=_required_str(raw, "transactionId"),
        original_transaction_id=_required_str(raw, "originalTransactionId"),
        bundle_id=_required_str(raw, "bundleId"),
        product_id=_required_str(raw, "productId"),
        purchase_date=_ms_to_datetime(raw, "purchaseDate", required=True),
        signed_date=_ms_to_datetime(raw, "signedDate", required=True),
        environment=_required_str(raw, "environment"),
        revocation_date=_ms_to_datetime(raw, "revocationDate", required=False),
        app_account_token=token.lower() if token else None,
    )


# ── entry point ──────────────────────────────────────────────────────────────

def verify_signed_transaction(jws: str) -> SignedTransaction:
    """Verify a StoreKit 2 ``jwsRepresentation`` and return its payload.

    Raises :class:`InvalidSignedTransaction` for every failure; the message
    names the failing check and never includes the token or the payload.
    """
    if not isinstance(jws, str):
        raise InvalidSignedTransaction("signed transaction is not a string")
    parts = jws.strip().split(".")
    if len(parts) != 3 or not all(parts):
        raise InvalidSignedTransaction("not a compact JWS")
    header_b64, payload_b64, signature_b64 = parts

    header = _json_object(_b64url_decode(header_b64), "header")
    if header.get("alg") != "ES256":
        raise InvalidSignedTransaction("alg is not ES256")

    leaf, intermediate = _certificates(header)[:2]
    _verify_chain(leaf, intermediate)
    if not _has_extension(leaf, LEAF_RECEIPT_SIGNING_OID):
        raise InvalidSignedTransaction("leaf lacks the App Store receipt-signing extension")
    if not _has_extension(intermediate, INTERMEDIATE_WWDR_OID):
        raise InvalidSignedTransaction("intermediate lacks the WWDR extension")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    _verify_signature(leaf, signing_input, _b64url_decode(signature_b64))

    transaction = _payload(_json_object(_b64url_decode(payload_b64), "payload"))
    _valid_at(leaf, transaction.signed_date, "leaf")
    _valid_at(intermediate, transaction.signed_date, "intermediate")
    return transaction
