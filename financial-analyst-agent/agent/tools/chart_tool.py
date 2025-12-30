"""Chart generation tool for financial data visualization.

This tool allows Claude to generate structured chart data that can be
rendered by the React frontend using Recharts.
"""

import json
from typing import Any, Dict
from agent.tools.base import Tool
from agent.utils.chart_schemas import ChartData


class GenerateGraphDataTool(Tool):
    """Tool for generating structured chart data."""

    def __init__(self):
        super().__init__(
            name="generate_graph_data",
            description="Generate structured JSON data for creating financial charts and graphs.",
            input_schema={
                "type": "object",
                "properties": {
                    "chartType": {
                        "type": "string",
                        "enum": ["bar", "multiBar", "line", "pie", "area", "stackedArea"],
                        "description": "The type of chart to generate",
                    },
                    "config": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "trend": {
                                "type": "object",
                                "properties": {
                                    "percentage": {"type": "number"},
                                    "direction": {
                                        "type": "string",
                                        "enum": ["up", "down"],
                                    },
                                },
                                "required": ["percentage", "direction"],
                            },
                            "footer": {"type": "string"},
                            "totalLabel": {"type": "string"},
                            "xAxisKey": {"type": "string"},
                        },
                        "required": ["title", "description"],
                    },
                    "data": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": True,  # Allow any structure
                        },
                    },
                    "chartConfig": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "stacked": {"type": "boolean"},
                            },
                            "required": ["label"],
                        },
                    },
                },
                "required": ["chartType", "config", "data", "chartConfig"],
            },
        )

    async def execute(self, **kwargs) -> str:
        """Execute the tool to generate chart data.

        Args:
            **kwargs: Chart data parameters matching the input schema

        Returns:
            JSON string of the validated chart data
        """
        try:
            # Validate with Pydantic
            chart_data = ChartData(**kwargs)

            # Process pie charts to ensure correct structure
            if chart_data.chartType == "pie":
                chart_data = self._process_pie_chart(chart_data)

            # Add color variables to chartConfig
            chart_data = self._add_color_variables(chart_data)

            # Convert to dict and return as JSON string
            return json.dumps(chart_data.model_dump(), indent=2)

        except Exception as e:
            # Return error message as string
            return json.dumps({"error": f"Error generating chart: {str(e)}"})

    def _process_pie_chart(self, chart_data: ChartData) -> ChartData:
        """Transform pie chart data to match expected structure.

        Pie charts should have 'segment' and 'value' fields.
        This method normalizes various input formats to this structure.

        Args:
            chart_data: The chart data to process

        Returns:
            Processed chart data with normalized pie chart structure
        """
        processed_data = []

        # Get the value key from chartConfig (first key)
        value_key = list(chart_data.chartConfig.keys())[0] if chart_data.chartConfig else "value"

        # Get the segment key from config or infer from data
        segment_key = chart_data.config.xAxisKey or "segment"

        for item in chart_data.data:
            # Try multiple possible segment keys
            segment = (
                item.get(segment_key)
                or item.get("segment")
                or item.get("category")
                or item.get("name")
                or item.get("label")
            )

            # Try multiple possible value keys
            value = item.get(value_key) or item.get("value") or item.get("amount")

            if segment and value is not None:
                processed_data.append({"segment": segment, "value": value})

        # Update the chart data
        chart_data.data = processed_data
        chart_data.config.xAxisKey = "segment"

        return chart_data

    def _add_color_variables(self, chart_data: ChartData) -> ChartData:
        """Add color CSS variables to chartConfig for consistent theming.

        Args:
            chart_data: The chart data to process

        Returns:
            Chart data with color variables added
        """
        for idx, (key, config) in enumerate(chart_data.chartConfig.items()):
            # Add color variable using CSS custom properties
            # This matches the Tailwind CSS --chart-N variables in the frontend
            chart_data.chartConfig[key]["color"] = f"hsl(var(--chart-{idx + 1}))"

        return chart_data
