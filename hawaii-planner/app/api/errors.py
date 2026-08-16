"""Shared HTTP error shapes — every failure serializes as {"error": {code, message}}."""
from fastapi import HTTPException


def bad_request(message: str, code: str = "invalid_request") -> HTTPException:
    return HTTPException(status_code=400, detail={"code": code, "message": message})


def not_found(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": code, "message": message})


def reject_null_fields(updates: dict, fields: tuple[str, ...]) -> None:
    """PATCH may omit a field, but must never null a column the app relies on."""
    for field in fields:
        if field in updates and updates[field] is None:
            raise bad_request(f"{field} cannot be null.")
