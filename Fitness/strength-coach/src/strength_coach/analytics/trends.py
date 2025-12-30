"""Exercise trend analysis and weekly rollups."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import pandas as pd

from .e1rm import E1RMFormula, estimate_e1rm


@dataclass
class TrendDirection:
    """Trend classification with percentage change."""

    direction: str  # "up", "down", "stable"
    change_pct: float

    @classmethod
    def from_change(cls, old_value: Decimal, new_value: Decimal) -> "TrendDirection":
        if old_value == 0:
            return cls(direction="stable", change_pct=0.0)

        pct_change = float((new_value - old_value) / old_value * 100)

        if pct_change > 2.0:
            return cls(direction="up", change_pct=pct_change)
        elif pct_change < -2.0:
            return cls(direction="down", change_pct=pct_change)
        else:
            return cls(direction="stable", change_pct=pct_change)


def exercise_sets_to_dataframe(sets_data: list[dict]) -> pd.DataFrame:
    """
    Convert exercise set history to a pandas DataFrame.

    Args:
        sets_data: List of set dictionaries from storage

    Returns:
        DataFrame with columns: session_date, weight_lb, reps, e1rm
    """
    if not sets_data:
        return pd.DataFrame(columns=["session_date", "weight_lb", "reps", "e1rm"])

    df = pd.DataFrame(sets_data)

    # Ensure proper types
    df["session_date"] = pd.to_datetime(df["session_date"]).dt.date
    df["weight_lb"] = pd.to_numeric(df["weight_lb"])
    df["reps"] = pd.to_numeric(df["reps"])

    # Calculate e1RM for each set
    df["e1rm"] = df.apply(
        lambda row: float(
            estimate_e1rm(Decimal(str(row["weight_lb"])), int(row["reps"]))
        ),
        axis=1,
    )

    return df


def get_weekly_best_e1rm(
    df: pd.DataFrame,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> pd.DataFrame:
    """
    Get the best e1RM per week for an exercise.

    Args:
        df: DataFrame with set data (must have session_date, e1rm, weight_lb, reps)
        start_date: Start of date range (optional)
        end_date: End of date range (optional)

    Returns:
        DataFrame with: week_start, best_e1rm, best_weight, best_reps
    """
    if df.empty:
        return pd.DataFrame(columns=["week_start", "best_e1rm", "best_weight", "best_reps"])

    # Filter by date range
    if start_date:
        df = df[df["session_date"] >= start_date]
    if end_date:
        df = df[df["session_date"] <= end_date]

    if df.empty:
        return pd.DataFrame(columns=["week_start", "best_e1rm", "best_weight", "best_reps"])

    # Add week start (Monday)
    df = df.copy()
    df["week_start"] = df["session_date"].apply(
        lambda d: d - timedelta(days=d.weekday())
    )

    # Group by week and get best set (highest e1RM)
    weekly = df.loc[df.groupby("week_start")["e1rm"].idxmax()]

    result = weekly[["week_start", "e1rm", "weight_lb", "reps"]].copy()
    result.columns = ["week_start", "best_e1rm", "best_weight", "best_reps"]
    result = result.sort_values("week_start").reset_index(drop=True)

    return result


def get_rolling_avg_e1rm(
    df: pd.DataFrame,
    window_weeks: int = 4,
) -> pd.DataFrame:
    """
    Calculate rolling N-week average of weekly best e1RM.

    Args:
        df: DataFrame from get_weekly_best_e1rm
        window_weeks: Rolling window size

    Returns:
        DataFrame with: week_start, best_e1rm, rolling_avg_e1rm
    """
    if df.empty:
        return pd.DataFrame(columns=["week_start", "best_e1rm", "rolling_avg_e1rm"])

    result = df[["week_start", "best_e1rm"]].copy()
    result["rolling_avg_e1rm"] = (
        result["best_e1rm"].rolling(window=window_weeks, min_periods=1).mean()
    )

    return result


def get_exercise_trend(
    sets_data: list[dict],
    weeks: int = 12,
    comparison_weeks: int = 4,
) -> dict:
    """
    Get comprehensive trend analysis for an exercise.

    Args:
        sets_data: Set history from storage
        weeks: How many weeks of data to analyze
        comparison_weeks: How many weeks back to compare

    Returns:
        Dictionary with trend data:
        - current_e1rm: Latest best e1RM
        - e1rm_n_weeks_ago: e1RM from comparison_weeks ago
        - e1rm_change_pct: Percentage change
        - trend_direction: "up", "down", or "stable"
        - weekly_data: List of weekly best e1RMs
        - volume_trend: Weekly set counts
    """
    if not sets_data:
        return {
            "current_e1rm": Decimal("0"),
            "e1rm_n_weeks_ago": Decimal("0"),
            "e1rm_change_pct": 0.0,
            "trend_direction": "insufficient_data",
            "weekly_data": [],
            "volume_trend": [],
        }

    df = exercise_sets_to_dataframe(sets_data)

    # Get date range
    end_date = date.today()
    start_date = end_date - timedelta(weeks=weeks)

    # Get weekly bests
    weekly_df = get_weekly_best_e1rm(df, start_date, end_date)

    if weekly_df.empty:
        return {
            "current_e1rm": Decimal("0"),
            "e1rm_n_weeks_ago": Decimal("0"),
            "e1rm_change_pct": 0.0,
            "trend_direction": "insufficient_data",
            "weekly_data": [],
            "volume_trend": [],
        }

    # Current e1RM (most recent week)
    current_e1rm = Decimal(str(weekly_df.iloc[-1]["best_e1rm"]))

    # e1RM from N weeks ago
    comparison_date = end_date - timedelta(weeks=comparison_weeks)
    past_data = weekly_df[weekly_df["week_start"] <= comparison_date]

    if past_data.empty:
        e1rm_n_weeks_ago = current_e1rm
    else:
        e1rm_n_weeks_ago = Decimal(str(past_data.iloc[-1]["best_e1rm"]))

    # Calculate trend
    trend = TrendDirection.from_change(e1rm_n_weeks_ago, current_e1rm)

    # Volume trend (sets per week)
    df_filtered = df[(df["session_date"] >= start_date) & (df["session_date"] <= end_date)]
    df_filtered = df_filtered.copy()
    df_filtered["week_start"] = df_filtered["session_date"].apply(
        lambda d: d - timedelta(days=d.weekday())
    )
    volume_by_week = df_filtered.groupby("week_start").size().reset_index(name="sets")

    return {
        "current_e1rm": current_e1rm,
        "e1rm_n_weeks_ago": e1rm_n_weeks_ago,
        "e1rm_change_pct": trend.change_pct,
        "trend_direction": trend.direction,
        "weekly_data": weekly_df.to_dict("records"),
        "volume_trend": volume_by_week.to_dict("records"),
    }


def compare_exercises(
    exercise_trends: dict[str, dict],
) -> list[dict]:
    """
    Compare trends across multiple exercises.

    Args:
        exercise_trends: Dict mapping exercise_id to trend data

    Returns:
        List of exercises sorted by progress (best to worst)
    """
    results = []

    for exercise_id, trend in exercise_trends.items():
        results.append(
            {
                "exercise_id": exercise_id,
                "current_e1rm": trend["current_e1rm"],
                "change_pct": trend["e1rm_change_pct"],
                "trend_direction": trend["trend_direction"],
            }
        )

    # Sort by change percentage (descending)
    results.sort(key=lambda x: x["change_pct"], reverse=True)

    return results
