"""Command line interface for generating semantic model YAML."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

from .client import CollibraGraphQLClient
from .pipeline import SemanticModelConfig, generate_semantic_model_yaml


def _load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        if path.endswith(".json"):
            return json.load(handle)
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise RuntimeError("PyYAML must be installed to load YAML config files") from exc
        return yaml.safe_load(handle)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Snowflake semantic model YAML from Collibra metadata")
    parser.add_argument("table", help="Physical Snowflake table name (e.g. DIM_CUSTOMER)")
    parser.add_argument("--database", required=True, help="Snowflake database name")
    parser.add_argument("--schema", required=True, help="Snowflake schema name")
    parser.add_argument("--collibra-url", default=os.environ.get("COLLIBRA_BASE_URL"), help="Collibra base URL")
    parser.add_argument("--auth-token", default=os.environ.get("COLLIBRA_AUTH_TOKEN"), help="Authorization header value")
    parser.add_argument("--config", help="Path to optional JSON/YAML config overriding attribute mappings")
    parser.add_argument("--skip-relationships", action="store_true", help="Disable relationship inference")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_argument_parser()
    args = parser.parse_args(argv)

    if not args.collibra_url:
        parser.error("Collibra base URL must be provided via --collibra-url or COLLIBRA_BASE_URL")
    if not args.auth_token:
        parser.error("Collibra API token must be provided via --auth-token or COLLIBRA_AUTH_TOKEN")

    config = SemanticModelConfig(
        collibra_base_url=args.collibra_url,
        auth_token=args.auth_token,
        database=args.database,
        schema=args.schema,
        table=args.table,
        include_relationships=not args.skip_relationships,
    )

    if args.config:
        overrides = _load_config(args.config) or {}
        attribute_mapping_kwargs = overrides.get("attribute_mapping", {})
        for field_name, value in attribute_mapping_kwargs.items():
            if hasattr(config.attribute_mapping, field_name):
                setattr(config.attribute_mapping, field_name, value)

    client = CollibraGraphQLClient(base_url=config.collibra_base_url, auth_token=config.auth_token)
    output = generate_semantic_model_yaml(config, client=client)
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
