"""Agent module for LLM integration."""

from .persona import (
    CoachPersona,
    DEFAULT_PERSONA,
    ENCOURAGING_PERSONA,
    ANALYTICAL_PERSONA,
)
from .prompt_builder import (
    build_user_context,
    build_recent_training_context,
    build_lift_progress_context,
    build_bodyweight_context,
    build_percentile_context,
    build_full_context,
    build_query_prompt,
    SUPPORTED_QUERIES,
)

__all__ = [
    "CoachPersona",
    "DEFAULT_PERSONA",
    "ENCOURAGING_PERSONA",
    "ANALYTICAL_PERSONA",
    "build_user_context",
    "build_recent_training_context",
    "build_lift_progress_context",
    "build_bodyweight_context",
    "build_percentile_context",
    "build_full_context",
    "build_query_prompt",
    "SUPPORTED_QUERIES",
]
