"""Body weight trend analysis."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import pandas as pd

from ..models import BodyWeightEntry


@dataclass
class WeightTrendAnalysis:
    """Results from weight trend analysis."""

    current_weight: Decimal
    rolling_7day_avg: Decimal
    rolling_14day_avg: Optional[Decimal]
    weekly_change_lb: Decimal
    weekly_change_pct: float
    trend_4wk: str  # "losing", "gaining", "stable"
    days_at_plateau: int  # 0 if not in plateau
    total_change_lb: Decimal  # From first to last entry
    alerts: list[str] = field(default_factory=list)
    data_quality: str = "good"  # "good", "sparse", "insufficient"


def entries_to_dataframe(entries: list[BodyWeightEntry]) -> pd.DataFrame:
    """Convert body weight entries to a pandas DataFrame."""
    if not entries:
        return pd.DataFrame(columns=["date", "weight_lb"])

    data = [
        {
            "date": e.date,
            "weight_lb": float(e.weight_lb),
            "time_of_day": e.time_of_day.value if e.time_of_day else None,
            "is_post_meal": e.is_post_meal,
        }
        for e in entries
    ]

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    return df


def calculate_rolling_average(
    df: pd.DataFrame,
    window_days: int = 7,
) -> pd.Series:
    """Calculate rolling average weight."""
    if df.empty:
        return pd.Series(dtype=float)

    # Resample to daily and forward fill gaps
    df_daily = df.set_index("date").resample("D")["weight_lb"].mean()
    df_daily = df_daily.ffill()

    return df_daily.rolling(window=window_days, min_periods=1).mean()


def detect_plateau(
    rolling_avg: pd.Series,
    threshold_lb: float = 0.5,
    min_days: int = 14,
) -> int:
    """
    Detect if currently in a weight plateau.

    Returns number of days at plateau (0 if not in plateau).
    """
    if len(rolling_avg) < min_days:
        return 0

    recent = rolling_avg.iloc[-min_days:]
    range_lb = recent.max() - recent.min()

    if range_lb <= threshold_lb:
        # Count consecutive days within threshold from end
        current = rolling_avg.iloc[-1]
        days = 0
        for val in reversed(rolling_avg.values):
            if abs(val - current) <= threshold_lb:
                days += 1
            else:
                break
        return days if days >= min_days else 0

    return 0


def analyze_weight_trends(
    entries: list[BodyWeightEntry],
    plateau_threshold_lb: float = 0.5,
    plateau_min_days: int = 14,
) -> WeightTrendAnalysis:
    """
    Comprehensive weight trend analysis.

    Args:
        entries: List of body weight entries
        plateau_threshold_lb: Max variance to consider a plateau
        plateau_min_days: Minimum days to qualify as plateau

    Returns:
        WeightTrendAnalysis with trend data and alerts
    """
    if not entries:
        return WeightTrendAnalysis(
            current_weight=Decimal("0"),
            rolling_7day_avg=Decimal("0"),
            rolling_14day_avg=None,
            weekly_change_lb=Decimal("0"),
            weekly_change_pct=0.0,
            trend_4wk="insufficient_data",
            days_at_plateau=0,
            total_change_lb=Decimal("0"),
            alerts=["No weight data available"],
            data_quality="insufficient",
        )

    df = entries_to_dataframe(entries)

    # Check data quality
    date_range = (df["date"].max() - df["date"].min()).days
    entries_per_week = len(df) / max(date_range / 7, 1)

    if len(entries) < 3:
        data_quality = "insufficient"
    elif entries_per_week < 2:
        data_quality = "sparse"
    else:
        data_quality = "good"

    # Current weight (most recent)
    current_weight = Decimal(str(df.iloc[-1]["weight_lb"]))

    # Rolling averages
    rolling = calculate_rolling_average(df, 7)
    rolling_7day = Decimal(str(rolling.iloc[-1])) if not rolling.empty else current_weight

    rolling_14 = calculate_rolling_average(df, 14)
    rolling_14day = Decimal(str(rolling_14.iloc[-1])) if len(rolling_14) >= 14 else None

    # Weekly change
    if len(rolling) >= 7:
        week_ago = Decimal(str(rolling.iloc[-7]))
        weekly_change = rolling_7day - week_ago
    else:
        weekly_change = Decimal("0")

    weekly_change_pct = float(weekly_change / week_ago * 100) if week_ago else 0

    # 4-week trend
    if len(rolling) >= 28:
        four_weeks_ago = Decimal(str(rolling.iloc[-28]))
        four_week_change = rolling_7day - four_weeks_ago
        if four_week_change > Decimal("1"):
            trend_4wk = "gaining"
        elif four_week_change < Decimal("-1"):
            trend_4wk = "losing"
        else:
            trend_4wk = "stable"
    else:
        trend_4wk = "insufficient_data"

    # Plateau detection
    plateau_days = detect_plateau(rolling, plateau_threshold_lb, plateau_min_days)

    # Total change
    first_weight = Decimal(str(df.iloc[0]["weight_lb"]))
    total_change = current_weight - first_weight

    # Generate alerts
    alerts: list[str] = []

    # Rapid weight change alert
    if abs(float(weekly_change)) > 2.0:
        direction = "gain" if weekly_change > 0 else "loss"
        alerts.append(f"Rapid weight {direction}: {abs(weekly_change):.1f} lb/week")

    # Plateau alert
    if plateau_days >= 21:
        alerts.append(f"Extended plateau: {plateau_days} days with minimal change")

    # Data quality alert
    if data_quality == "sparse":
        alerts.append("Sparse data: consider weighing more frequently for accuracy")

    return WeightTrendAnalysis(
        current_weight=current_weight,
        rolling_7day_avg=rolling_7day,
        rolling_14day_avg=rolling_14day,
        weekly_change_lb=weekly_change,
        weekly_change_pct=round(weekly_change_pct, 2),
        trend_4wk=trend_4wk,
        days_at_plateau=plateau_days,
        total_change_lb=total_change,
        alerts=alerts,
        data_quality=data_quality,
    )


def get_weight_history_summary(
    entries: list[BodyWeightEntry],
    weeks: int = 12,
) -> list[dict]:
    """
    Get weekly weight summary for the past N weeks.

    Returns list of weekly averages.
    """
    if not entries:
        return []

    df = entries_to_dataframe(entries)
    today = pd.Timestamp.today()
    start_date = today - pd.Timedelta(weeks=weeks)

    df_filtered = df[df["date"] >= start_date]

    if df_filtered.empty:
        return []

    # Add week start
    df_filtered = df_filtered.copy()
    df_filtered["week_start"] = df_filtered["date"].dt.to_period("W").dt.start_time

    weekly = df_filtered.groupby("week_start").agg(
        avg_weight=("weight_lb", "mean"),
        min_weight=("weight_lb", "min"),
        max_weight=("weight_lb", "max"),
        entries=("weight_lb", "count"),
    ).reset_index()

    return [
        {
            "week_start": row["week_start"].strftime("%Y-%m-%d"),
            "avg_weight": round(row["avg_weight"], 1),
            "min_weight": round(row["min_weight"], 1),
            "max_weight": round(row["max_weight"], 1),
            "entries": int(row["entries"]),
        }
        for _, row in weekly.iterrows()
    ]
