"""Collibra-enriched Snowflake semantic model generator."""

from .pipeline import generate_semantic_model_yaml, SemanticModelConfig

__all__ = [
    "generate_semantic_model_yaml",
    "SemanticModelConfig",
]
