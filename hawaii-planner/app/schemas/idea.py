"""Idea and vote request schemas."""
from typing import Literal

from pydantic import BaseModel, Field

MealTag = Literal["breakfast", "lunch", "dinner", "treat"]


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


class IdeaPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    region_id: str | None = None
    duration_min: int | None = Field(default=None, ge=5, le=720)
    yelp_url: str | None = None
    maps_url: str | None = None
    notes: str | None = None
    best_time: str | None = None
    meal_tags: list[MealTag] | None = None


class VoteIn(BaseModel):
    value: Literal["interested", "must_go"]
