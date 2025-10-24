"""Dataclasses that represent Snowflake semantic model entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Dimension:
    name: str
    description: str
    expr: str
    data_type: str
    synonyms: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "name": self.name,
            "description": self.description,
            "expr": self.expr,
            "data_type": self.data_type,
        }
        if self.synonyms:
            payload["synonyms"] = self.synonyms
        return payload


@dataclass
class Metric:
    name: str
    description: str
    expr: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "expr": self.expr,
        }


@dataclass
class Relationship:
    name: str
    description: str
    source_table: str
    target_table: str
    join_type: str
    join_condition: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "source_table": self.source_table,
            "target_table": self.target_table,
            "join_type": self.join_type,
            "join_condition": self.join_condition,
        }


@dataclass
class Table:
    name: str
    description: str
    base_table: Dict[str, str]
    dimensions: List[Dimension]
    metrics: List[Metric]
    primary_key: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "name": self.name,
            "description": self.description,
            "base_table": self.base_table,
            "dimensions": [dim.to_dict() for dim in self.dimensions],
            "metrics": [metric.to_dict() for metric in self.metrics],
        }
        if self.primary_key:
            payload["primary_key"] = {"columns": self.primary_key}
        return payload


@dataclass
class SemanticModel:
    name: str
    description: str
    tables: List[Table]
    relationships: List[Relationship] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "name": self.name,
            "description": self.description,
            "tables": [table.to_dict() for table in self.tables],
        }
        if self.relationships:
            payload["relationships"] = [rel.to_dict() for rel in self.relationships]
        return payload
