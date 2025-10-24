"""High-level orchestration for building semantic model YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from .client import CollibraGraphQLClient
from .models import Dimension, Metric, Relationship, SemanticModel, Table
from .serialization import dump_yaml
from .utils import coalesce_first, normalize_synonyms, strip_html

# GraphQL query templates ---------------------------------------------------

_TABLE_QUERY = """
query GetTable($tableName: String!, $tableType: String!, $limit: Int) {
  assets(
    where: {
      _and: [
        { type: { name: { eq: $tableType } } }
        { displayName: { eq: $tableName } }
      ]
    }
    limit: $limit
  ) {
    id
    displayName
    description
    multiValueAttributes {
      type { name }
      stringValues
    }
    outgoingRelations {
      type { name }
      target {
        id
        displayName
        type { name }
      }
    }
    incomingRelations {
      type { name }
      source {
        id
        displayName
        type { name }
      }
    }
  }
}
"""

_COLUMNS_QUERY = """
query GetColumns($tableId: ID!, $columnType: String!, $relationType: String!, $limit: Int) {
  assets(
    where: {
      _and: [
        { type: { name: { eq: $columnType } } }
        { incomingRelations: {
            some: {
              type: { name: { eq: $relationType } }
              source: { id: { eq: $tableId } }
            }
          }
        }
      ]
    }
    limit: $limit
  ) {
    id
    displayName
    description
    multiValueAttributes {
      type { name }
      stringValues
    }
    outgoingRelations {
      type { name }
      target {
        id
        displayName
        type { name }
      }
    }
    incomingRelations {
      type { name }
      source {
        id
        displayName
        type { name }
      }
    }
  }
}
"""

_PARENT_TABLE_QUERY = """
query GetParentTable($columnId: ID!, $tableType: String!, $relationType: String!) {
  assets(
    where: {
      _and: [
        { id: { eq: $columnId } }
        { type: { name: { eq: "Column" } } }
      ]
    }
    limit: 1
  ) {
    incomingRelations(
      where: {
        _and: [
          { type: { name: { eq: $relationType } } }
          { source: { type: { name: { eq: $tableType } } } }
        ]
      }
    ) {
      source {
        id
        displayName
      }
    }
  }
}
"""

# Configuration -------------------------------------------------------------


@dataclass
class AttributeMapping:
    description: List[str] = field(default_factory=lambda: ["Definition", "Business Definition"])
    synonyms: List[str] = field(default_factory=lambda: ["Business Name", "Alias", "Synonym", "Synonyms"])
    data_type: List[str] = field(default_factory=lambda: ["Data Type", "Datatype", "Column Data Type"])
    primary_key: List[str] = field(default_factory=lambda: ["Primary Key", "Is Primary Key"])


@dataclass
class SemanticModelConfig:
    collibra_base_url: str
    auth_token: str
    database: str
    schema: str
    table: str
    table_type: str = "Table"
    column_type: str = "Column"
    column_relation_type: str = "is part of"
    foreign_key_relation_names: List[str] = field(default_factory=lambda: ["Foreign key", "Foreign key to", "References"])
    attribute_mapping: AttributeMapping = field(default_factory=AttributeMapping)
    include_relationships: bool = True
    max_assets: int = 500

    def build_client(self) -> CollibraGraphQLClient:
        return CollibraGraphQLClient(base_url=self.collibra_base_url, auth_token=self.auth_token)


# Extraction helpers -------------------------------------------------------


def _extract_attribute(values: Iterable[Dict[str, Any]], target_names: Iterable[str]) -> List[str]:
    target_lower = {name.lower() for name in target_names}
    collected: List[str] = []
    for attribute in values:
        attr_type = attribute.get("type", {}).get("name", "").lower()
        if attr_type in target_lower:
            collected.extend(attribute.get("stringValues", []) or [])
    return collected


def _is_primary_key(attribute_values: Iterable[Dict[str, Any]], relation_values: Iterable[Dict[str, Any]], mapping: AttributeMapping) -> bool:
    for value in _extract_attribute(attribute_values, mapping.primary_key):
        if value.lower() in {"true", "yes", "1"}:
            return True
    for relation in relation_values:
        relation_name = relation.get("type", {}).get("name", "").lower()
        if "primary key" in relation_name:
            return True
    return False


def _collect_synonyms(attribute_values: Iterable[Dict[str, Any]], relation_values: Iterable[Dict[str, Any]], mapping: AttributeMapping) -> List[str]:
    synonyms: List[str] = []
    synonyms.extend(_extract_attribute(attribute_values, mapping.synonyms))
    for relation in relation_values:
        relation_name = relation.get("type", {}).get("name", "").lower()
        if "synonym" in relation_name:
            target = relation.get("target") or relation.get("source")
            if target and target.get("displayName"):
                synonyms.append(target["displayName"])
    return normalize_synonyms(synonyms)


def _map_columns_to_dimensions(columns: Iterable[Dict[str, Any]], mapping: AttributeMapping) -> tuple[List[Dimension], List[str]]:
    dimensions: List[Dimension] = []
    primary_keys: List[str] = []

    for column in columns:
        name = column.get("displayName", "").upper()
        if not name:
            continue
        description_attr = _extract_attribute(column.get("multiValueAttributes", []), mapping.description)
        description = strip_html(coalesce_first(description_attr, column.get("description"))) or f"{name} column"
        synonyms = _collect_synonyms(column.get("multiValueAttributes", []), column.get("outgoingRelations", []), mapping)
        data_type_values = _extract_attribute(column.get("multiValueAttributes", []), mapping.data_type)
        data_type = coalesce_first(data_type_values) or "UNKNOWN"
        if _is_primary_key(column.get("multiValueAttributes", []), column.get("outgoingRelations", []), mapping):
            primary_keys.append(name)
        dimensions.append(
            Dimension(
                name=name,
                description=description,
                expr=name,
                data_type=data_type,
                synonyms=synonyms,
            )
        )
    return dimensions, primary_keys


# Relationship handling ----------------------------------------------------


def _collect_relationships(columns: Iterable[Dict[str, Any]], table_name: str, client: CollibraGraphQLClient, config: SemanticModelConfig) -> List[Relationship]:
    relationships: List[Relationship] = []
    if not config.include_relationships:
        return relationships

    foreign_key_names = {name.lower() for name in config.foreign_key_relation_names}

    for column in columns:
        source_column_name = column.get("displayName")
        if not source_column_name:
            continue
        for relation in column.get("outgoingRelations", []):
            relation_name = relation.get("type", {}).get("name", "").lower()
            if relation_name not in foreign_key_names:
                continue
            target = relation.get("target")
            if not target or target.get("type", {}).get("name") != config.column_type:
                continue

            target_column_name = target.get("displayName")
            if not target_column_name:
                continue

            parent_table = _lookup_parent_table(client, target.get("id"), config)
            if not parent_table:
                continue

            target_table_name = parent_table["displayName"].upper()
            relationship_name = f"{table_name}_TO_{target_table_name}"
            relationships.append(
                Relationship(
                    name=relationship_name,
                    description=f"Join between {table_name} and {target_table_name}",
                    source_table=table_name,
                    target_table=target_table_name,
                    join_type="many_to_one",
                    join_condition=f"{table_name}.{source_column_name.upper()} = {target_table_name}.{target_column_name.upper()}",
                )
            )
    return relationships


def _lookup_parent_table(client: CollibraGraphQLClient, column_id: str, config: SemanticModelConfig) -> Optional[Dict[str, Any]]:
    variables = {
        "columnId": column_id,
        "tableType": config.table_type,
        "relationType": config.column_relation_type,
    }
    data = client.execute(_PARENT_TABLE_QUERY, variables)
    assets = data.get("assets") or []
    if not assets:
        return None
    relations = assets[0].get("incomingRelations") or []
    if not relations:
        return None
    # Expecting a single relation pointing to the parent table.
    source = relations[0].get("source")
    return source


# Metrics ------------------------------------------------------------------


def _build_default_metrics(table_name: str, primary_keys: List[str]) -> List[Metric]:
    metrics: List[Metric] = []
    if primary_keys:
        pk = primary_keys[0]
        metrics.append(
            Metric(
                name=f"{table_name}_COUNT",
                description=f"Count of distinct {table_name}",
                expr=f"COUNT(DISTINCT {pk})",
            )
        )
    metrics.append(
        Metric(
            name=f"{table_name}_ROW_COUNT",
            description=f"Row count of {table_name}",
            expr="COUNT(*)",
        )
    )
    return metrics


# Public API ---------------------------------------------------------------


def build_semantic_model(config: SemanticModelConfig, client: Optional[CollibraGraphQLClient] = None) -> SemanticModel:
    """Return a :class:`SemanticModel` built from Collibra metadata."""

    if client is None:
        client = config.build_client()

    table_data = client.execute(
        _TABLE_QUERY,
        {
            "tableName": config.table,
            "tableType": config.table_type,
            "limit": 1,
        },
    ).get("assets")

    if not table_data:
        raise ValueError(f"Collibra table asset not found for {config.table}")

    table_asset = table_data[0]
    table_name = table_asset.get("displayName", config.table).upper()
    table_description = strip_html(
        coalesce_first(
            _extract_attribute(table_asset.get("multiValueAttributes", []), config.attribute_mapping.description),
            table_asset.get("description"),
        )
    ) or f"Semantic model for {table_name}"

    columns = client.execute(
        _COLUMNS_QUERY,
        {
            "tableId": table_asset["id"],
            "columnType": config.column_type,
            "relationType": config.column_relation_type,
            "limit": config.max_assets,
        },
    ).get("assets", [])

    dimensions, primary_keys = _map_columns_to_dimensions(columns, config.attribute_mapping)

    relationships: List[Relationship] = _collect_relationships(columns, table_name, client, config)

    table = Table(
        name=table_name,
        description=table_description or f"{table_name} table",
        base_table={
            "database": config.database,
            "schema": config.schema,
            "table": config.table,
        },
        dimensions=sorted(dimensions, key=lambda d: d.name),
        metrics=_build_default_metrics(table_name, primary_keys),
        primary_key=sorted(set(primary_keys)),
    )

    semantic_model = SemanticModel(
        name=f"{table_name}_MODEL",
        description=table_description,
        tables=[table],
        relationships=relationships,
    )

    return semantic_model


def generate_semantic_model_yaml(config: SemanticModelConfig, client: Optional[CollibraGraphQLClient] = None) -> str:
    """Generate a Snowflake semantic model YAML string."""

    model = build_semantic_model(config, client=client)
    return dump_yaml(model.to_dict())
