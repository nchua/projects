"""Body weight and composition tracking models."""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .workout import WeightUnit, LB_TO_KG, KG_TO_LB


class TimeOfDay(str, Enum):
    """When the weigh-in occurred."""

    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class MeasurementMethod(str, Enum):
    """How body composition was measured."""

    SCALE = "scale"
    SCALE_BIA = "scale_bia"  # Bioelectrical impedance
    CALIPERS = "calipers"
    DEXA = "dexa"
    VISUAL = "visual"


class BodyWeightEntry(BaseModel):
    """A single body weight measurement."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    date: date
    weight: Decimal = Field(gt=0)
    weight_unit: WeightUnit = WeightUnit.LB
    time_of_day: Optional[TimeOfDay] = None
    bodyfat_percent: Optional[float] = Field(None, ge=3, le=60)
    measurement_method: Optional[MeasurementMethod] = None
    notes: Optional[str] = None
    is_post_meal: bool = False  # For data quality flagging

    @field_validator("weight", mode="before")
    @classmethod
    def coerce_weight(cls, v: float | int | str | Decimal) -> Decimal:
        return Decimal(str(v))

    @property
    def weight_lb(self) -> Decimal:
        """Return weight in pounds."""
        if self.weight_unit == WeightUnit.LB:
            return self.weight
        return (self.weight * KG_TO_LB).quantize(Decimal("0.1"))

    @property
    def weight_kg(self) -> Decimal:
        """Return weight in kilograms."""
        if self.weight_unit == WeightUnit.KG:
            return self.weight
        return (self.weight * LB_TO_KG).quantize(Decimal("0.01"))

    @property
    def lean_mass_lb(self) -> Decimal | None:
        """Estimated lean body mass in pounds, if body fat available."""
        if self.bodyfat_percent is None:
            return None
        fat_mass = self.weight_lb * Decimal(str(self.bodyfat_percent / 100))
        return self.weight_lb - fat_mass


class UserProfile(BaseModel):
    """User physical profile for calculations."""

    sex: str = Field(pattern="^(male|female)$")
    age: int = Field(ge=10, le=100)
    height_inches: float = Field(gt=0)
    default_bodyweight_lb: Decimal = Field(gt=0)
    training_start_date: Optional[date] = None

    @property
    def height_cm(self) -> float:
        """Height in centimeters."""
        return self.height_inches * 2.54

    @property
    def training_years(self) -> float | None:
        """Years of training experience."""
        if self.training_start_date is None:
            return None
        delta = date.today() - self.training_start_date
        return delta.days / 365.25


# Default user profile (as specified)
DEFAULT_USER_PROFILE = UserProfile(
    sex="male",
    age=29,
    height_inches=69,  # 5'9"
    default_bodyweight_lb=Decimal("166"),
)
