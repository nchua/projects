"""Idea and vote request schemas."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MealTag = Literal["breakfast", "lunch", "dinner", "treat"]


def _http_only(value: str | None) -> str | None:
    """Links render as tappable hrefs — reject non-http schemes (javascript: etc.)."""
    if value and not value.startswith(("http://", "https://")):
        raise ValueError("must be an http(s) URL")
    return value


class IdeaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    kind: Literal["activity", "restaurant"]
    region_id: str
    duration_min: int | None = Field(default=None, ge=5, le=720)
    yelp_url: str | None = None
    maps_url: str | None = None
    notes: str | None = None
    best_time: str | None = None
    meal_tags: list[MealTag] = []

    _urls = field_validator("yelp_url", "maps_url")(_http_only)


class IdeaPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    region_id: str | None = None
    duration_min: int | None = Field(default=None, ge=5, le=720)
    yelp_url: str | None = None
    maps_url: str | None = None
    notes: str | None = None
    best_time: str | None = None
    meal_tags: list[MealTag] | None = None

    _urls = field_validator("yelp_url", "maps_url")(_http_only)


class VoteIn(BaseModel):
    value: Literal["interested", "must_go"]
