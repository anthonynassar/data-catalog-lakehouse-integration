# Data Catalog Lakehouse Integration

This repository contains a Python toolkit for generating Snowflake semantic
model YAML files enriched with metadata sourced from Collibra.  It includes a
GraphQL client, metadata mapping utilities, and a CLI that transforms Collibra
assets into Snowflake-ready YAML.

## Getting started

Create and activate a virtual environment, then install the project with the
optional development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Generating semantic model YAML

Set your Collibra connection information and invoke the CLI:

```bash
export COLLIBRA_BASE_URL="https://your-collibra.example.com"
export COLLIBRA_AUTH_TOKEN="Bearer <token>"

python -m collibra_semantic_model.cli DIM_CUSTOMER \
  --database PROD_DB \
  --schema MART_CUSTOMER
```

The command prints the semantic model YAML to standard output.  Redirect the
result to a file or pipe it directly into
`SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML` within Snowflake.

### Optional configuration overrides

You can customise which Collibra attribute names represent descriptions,
Synonyms, and other metadata fields by supplying a JSON or YAML configuration
file:

```bash
python -m collibra_semantic_model.cli DIM_CUSTOMER \
  --database PROD_DB \
  --schema MART_CUSTOMER \
  --config config/attribute_mapping.yaml
```

Example configuration snippet:

```yaml
attribute_mapping:
  description:
    - Business Definition
    - Definition
  synonyms:
    - Alias
    - Business Name
```

Set `--skip-relationships` to avoid inferring foreign-key joins when your
Collibra catalog does not maintain those relations.

## Running tests

Execute the automated test suite with:

```bash
pytest
```

## Design documentation

The architectural rationale, API mapping, and development roadmap live in
[`docs/collibra_snowflake_semantic_model_design.md`](docs/collibra_snowflake_semantic_model_design.md).
