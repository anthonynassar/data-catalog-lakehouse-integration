# Collibra-Enriched Snowflake Semantic Model Pipeline

## 1. Objective
Design and implement an automated pipeline that generates Snowflake semantic model YAML files enriched with business metadata sourced from Collibra. The output YAML must closely match Snowflake's semantic model specification so it can be deployed via `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML` and expose business-friendly models for tools like Cortex Analyst.

## 2. High-Level Flow
1. **Select Target Tables**: Identify Snowflake tables (database, schema, table) that require semantic modeling.
2. **Resolve Collibra Assets**: Locate the corresponding Collibra `Table` asset for each Snowflake table.
3. **Harvest Metadata**: Use the Collibra Knowledge Graph API (GraphQL) as the primary interface to pull table-, column-, and relationship-level metadata. Fall back to REST v2 endpoints for gaps.
4. **Transform Metadata**: Map Collibra attributes and relations into Snowflake semantic model constructs (tables, dimensions, metrics, relationships).
5. **Generate YAML**: Assemble the enriched semantic model YAML structure and persist it (file system, Git, or S3).
6. **Publish to Snowflake**: Execute `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML` to apply the semantic model to the desired database/schema.
7. **Monitor & Iterate**: Log pipeline activity, handle errors, and schedule reruns when Collibra metadata changes.

## 3. Inputs and Outputs
| Item | Description |
| --- | --- |
| **Inputs** | List of Snowflake tables to model; Collibra API credentials; Collibra asset configuration (type names, relation types). |
| **Outputs** | One YAML document per semantic model (stored in VCS); optional Snowflake semantic view objects created via SQL procedure. |

## 4. Collibra Metadata Mapping
### 4.1 Table-Level Mapping
| Snowflake YAML field | Collibra source |
| --- | --- |
| `tables[].name` | `Table` asset `displayName` (business-friendly). |
| `tables[].description` | `Table` asset `description` or multi-value attribute `Definition`. Strip HTML. |
| `tables[].base_table.database/schema/table` | Collibra attributes like `Database Name`, `Schema Name`, `Table Name`; default to Snowflake input if missing. |
| `tables[].primary_key.columns` | Column assets flagged as PK (attribute `Primary Key` true or relation type containing "primary key"). |
| `tables[].dimensions` | Column assets related via "is part of" (or tenant-specific relation). |
| `tables[].metrics` | KPI/Metric assets linked to table; otherwise synthesize defaults (e.g., `COUNT(*)`, `COUNT(DISTINCT <PK>)`). |

### 4.2 Column to Dimension Mapping
| Snowflake YAML dimension field | Collibra source |
| --- | --- |
| `name` | Column asset `displayName` (uppercase). |
| `description` | `description` or `Definition` attribute (HTML stripped). |
| `synonyms[]` | Multi-value attributes (`Business Name`, `Alias`, `Synonym`, etc.) or relations ("synonym of"). |
| `expr` | Physical column name (uppercase). |
| `data_type` | Attribute `Data Type`. |

### 4.3 Relationships Mapping
* Collibra relations such as "Foreign key to", "References", or lineage-derived relations indicate joins.
* Build `relationships[]` entries:
  * `source_table` / `target_table`: parent table names resolved from related column assets.
  * `join_type`: infer `one_to_many` for PK→FK, `many_to_one` otherwise.
  * `join_condition`: `SOURCE.COLUMN = TARGET.COLUMN` composed from FK relation endpoints.
* If no FK metadata exists, omit relationships for that table.

### 4.4 Metrics Mapping
* Prefer Collibra KPI/Metric assets:
  * Attributes: `Name`, `Definition`, `Expression` (SQL or natural language).
  * Relation linking metric to table/columns.
* Fallback metrics:
  * `ROW_COUNT`: `COUNT(*)` for tables without PK.
  * `DISTINCT_<PK>_COUNT`: `COUNT(DISTINCT <PK>)` when PK exists.

## 5. Collibra API Integration
### 5.1 Authentication
* Support OAuth 2.0 client credentials or basic auth per tenant configuration.
* Store credentials in secrets manager; inject via environment variables.

### 5.2 Preferred GraphQL Query Patterns
Use the Knowledge Graph endpoint `POST /graphql/knowledgeGraph/v1` with queries that fetch nested attributes and relations.

#### Table Query Template
```graphql
query ($tableName: String!, $tableType: String!) {
  assets(
    where: {
      _and: [
        { type: { name: { eq: $tableType } } }
        { displayName: { eq: $tableName } }
      ]
    }
    limit: 1
  ) {
    id
    displayName
    description
    multiValueAttributes { type { name } stringValues }
    outgoingRelations {
      type { name }
      target { id displayName type { name } }
    }
    incomingRelations {
      type { name }
      source { id displayName type { name } }
    }
  }
}
```

#### Column Query Template
```graphql
query ($tableId: ID!, $columnType: String!, $relationType: String!) {
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
    limit: 500
  ) {
    id
    displayName
    description
    multiValueAttributes { type { name } stringValues }
    outgoingRelations { type { name } target { id displayName type { name } } }
    incomingRelations { type { name } source { id displayName type { name } } }
  }
}
```

### 5.3 REST Fallbacks
* `GET /rest/2.0/assets?name=...&typeId=...` to locate assets.
* `GET /rest/2.0/attributes?assetId=...` for additional attributes not exposed in GraphQL.
* `GET /rest/2.0/relations?sourceId=...` to enumerate relations when GraphQL scope is insufficient.

## 6. Pipeline Architecture
### 6.1 Components
1. **Configuration Loader**
   * Accepts target tables and tenant-specific Collibra type/relation names.
2. **Collibra Client**
   * Handles authentication, GraphQL requests, rate limiting, retries.
3. **Metadata Normalizer**
   * Cleans HTML, normalizes casing, deduplicates synonyms.
4. **Model Builder**
   * Translates normalized metadata into Snowflake YAML structure.
5. **YAML Renderer**
   * Serializes to YAML, enforces ordering, optional linting.
6. **Publisher**
   * Writes YAML to disk/Git.
   * Optional Snowflake publisher executing `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML` via Snowflake Python connector.
7. **Orchestrator**
   * Coordinates steps for each table; can run as Airflow DAG, scheduled job, or CLI tool.

### 6.2 Data Flow Diagram
```
Snowflake Table List → Orchestrator → Collibra Client → Raw Metadata
                                            ↓
                                    Metadata Normalizer → Model Builder → YAML Renderer → Semantic YAML File
                                                                                ↓
                                                                           Snowflake Publisher (optional)
```

## 7. Detailed Step-by-Step Algorithm
1. **Load configuration** for current run (target table identifiers, Collibra naming overrides, output paths).
2. **Resolve table asset**:
   * Query Collibra GraphQL for asset type `Table` (or configured type) with `displayName` matching the physical table name.
   * If multiple matches, apply disambiguation (database/schema attributes).
3. **Extract table metadata**:
   * Pull description and attributes such as database, schema, physical table name.
4. **Fetch column assets**:
   * Query Collibra for `Column` assets linked via relation `is part of` (configurable).
5. **Process each column**:
   * Description: prefer `description`, fallback to `Definition` attribute. Strip HTML.
   * Synonyms: collect multi-value attributes (`Business Name`, `Alias`, `Synonym`), dedupe.
   * Data type: read from `Data Type` attribute.
   * Primary key: detect via `Primary Key` attribute or relations containing "primary".
   * Sensitive tags: optionally collect attributes like `PII Flag` for downstream governance.
6. **Collect relationships**:
   * For each column, inspect outgoing relations with types containing `foreign key`, `references`, or configured names.
   * Resolve the target column's parent table (requires caching table lookups by column ID).
   * Build join metadata; infer `join_type` from PK/FK context.
7. **Derive metrics**:
   * Query Collibra for KPI assets linked to the table.
   * If none, generate fallback metrics.
8. **Assemble YAML structure**:
   * Compose top-level model with `name`, `description`.
   * Add table entry with `base_table`, `primary_key`, `dimensions`, `metrics`.
   * Append `relationships` if any.
9. **Serialize to YAML**:
   * Use `yaml.safe_dump` with `sort_keys=False` to preserve order.
   * Optionally run a YAML formatter (e.g., `ruamel.yaml`) to match team style.
10. **Persist output**:
    * Write to `semantic_models/<table>.yaml`.
    * Commit to Git if running in CI.
11. **Optional deployment**:
    * Call Snowflake via Python connector: `cursor.execute("CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(%s, %s)", ("DB.SCHEMA", yaml_text))`.
12. **Logging & Monitoring**:
    * Capture API latency, missing metadata warnings, YAML generation status.
    * Emit metrics/logs to observability stack.

## 8. Error Handling & Edge Cases
* **Missing assets**: If Collibra lacks a table/column asset, log and skip YAML generation for that table.
* **Ambiguous matches**: Implement filtering by schema/database attributes to avoid incorrect mappings.
* **Rate limiting**: Honor Collibra API limits; include exponential backoff and request throttling.
* **HTML descriptions**: Ensure stripping retains bullet lists (convert `<li>` to `-`).
* **Localization**: Handle UTF-8 characters in descriptions/synonyms.
* **Security classifications**: Optionally tag dimensions with governance info in description or custom YAML fields.

## 9. Operational Considerations
* **Scheduling**: Nightly or on-demand runs triggered by Collibra metadata updates.
* **Versioning**: Store generated YAML in Git to track changes and support review workflows.
* **Testing**: Unit-test metadata transformation functions with fixture payloads; integration-test against sandbox Collibra tenant.
* **Extensibility**: Parameterize asset type names and relation labels to support different Collibra configurations.

## 10. Implementation Pseudocode
```python
import requests
import yaml
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class CollibraConfig:
    url: str
    token: str
    table_type: str = "Table"
    column_type: str = "Column"
    table_column_relation: str = "is part of"
    fk_relation_names: List[str] = field(default_factory=lambda: ["Foreign key", "References"])
    synonym_attribute_names: List[str] = field(default_factory=lambda: ["Business Name", "Alias", "Synonym", "Synonyms"])
    definition_attribute_names: List[str] = field(default_factory=lambda: ["Definition", "Business Definition"])
    datatype_attribute_names: List[str] = field(default_factory=lambda: ["Data Type", "Datatype"])
    primary_key_attribute_names: List[str] = field(default_factory=lambda: ["Primary Key", "Is Primary Key"])

class CollibraClient:
    def __init__(self, config: CollibraConfig):
        self.config = config
        self.headers = {
            "Authorization": config.token,
            "Content-Type": "application/json",
        }

    def gql(self, query: str, variables: Optional[Dict] = None) -> Dict:
        resp = requests.post(
            f"{self.config.url}/graphql/knowledgeGraph/v1",
            headers=self.headers,
            json={"query": query, "variables": variables or {}},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "errors" in payload:
            raise RuntimeError(payload["errors"])
        return payload["data"]

    # Additional REST helpers can be added here.

def strip_html(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return raw
    text = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\s+", " ", text).strip()

# Additional transformation helpers omitted for brevity.
```

## 11. Deployment Workflow
1. **Local development**: Engineer runs CLI tool against sandbox Collibra tenant, verifies generated YAML.
2. **Code review**: Push changes and generated YAML to Git; reviewers validate mappings.
3. **CI pipeline**: Automated tests run; optionally validate YAML schema.
4. **Promotion**: Merge triggers job that regenerates YAML and publishes to Snowflake staging/production.

## 12. Future Enhancements
* **Bidirectional sync**: Push Snowflake lineage back to Collibra for closed-loop governance.
* **Delta detection**: Compare new YAML with previous version to surface metadata drifts.
* **UI layer**: Provide dashboard for business users to preview semantic models before deployment.
* **Metadata caching**: Cache Collibra responses to reduce API load and improve performance.

