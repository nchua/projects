"""Pydantic models for chart data validation.

These models mirror the TypeScript types from the Next.js application
to ensure compatibility between the Python backend and React frontend.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional, Literal


class TrendData(BaseModel):
    """Trend information for charts."""
    percentage: float = Field(..., description="Percentage change")
    direction: Literal["up", "down"] = Field(..., description="Direction of trend")


class ChartConfig(BaseModel):
    """Configuration for chart display."""
    title: str = Field(..., description="Chart title")
    description: str = Field(..., description="Chart description")
    trend: Optional[TrendData] = Field(None, description="Trend information")
    footer: Optional[str] = Field(None, description="Footer text")
    totalLabel: Optional[str] = Field(None, description="Label for total (pie charts)")
    xAxisKey: Optional[str] = Field(None, description="Key for x-axis data")


class ChartData(BaseModel):
    """Complete chart data structure."""
    chartType: Literal["bar", "multiBar", "line", "pie", "area", "stackedArea"] = Field(
        ..., description="Type of chart to render"
    )
    config: ChartConfig = Field(..., description="Chart configuration")
    data: List[Dict[str, Any]] = Field(..., description="Chart data points")
    chartConfig: Dict[str, Dict[str, Any]] = Field(
        ..., description="Configuration for chart series"
    )

    class Config:
        # Allow extra fields for flexibility
        extra = "allow"
