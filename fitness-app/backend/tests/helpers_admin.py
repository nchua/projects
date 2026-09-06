"""Shared helpers for the control-plane (admin) tests."""
from __future__ import annotations

from types import ModuleType
from typing import Any

from starlette.requests import Request

from app.services import entitlement_service as es
from tests.helpers_migrations import BACKEND, load_module


def make_request(path: str = "/admin/me", method: str = "GET") -> Request:
    """A bare Starlette request for calling dependencies directly."""
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "query_string": b"",
        }
    )


def load_script(name: str) -> ModuleType:
    return load_module(BACKEND / "scripts" / f"{name}.py", f"owner_script_{name}")


def grant_admin(db, user_id: str, key: str, value: Any):
    """Admin-sourced grant with the common arguments filled in (no commit)."""
    return es.grant(db, user_id=user_id, key=key, value=value, source="admin_grant")
