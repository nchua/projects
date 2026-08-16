"""Member request schemas."""
from pydantic import BaseModel, Field


class MemberClaim(BaseModel):
    name: str = Field(min_length=1, max_length=40)
