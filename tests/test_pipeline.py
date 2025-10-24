from collibra_semantic_model.pipeline import (
    SemanticModelConfig,
    build_semantic_model,
    generate_semantic_model_yaml,
)


class FakeClient:
    def execute(self, query, variables=None):
        if "GetTable" in query:
            return {
                "assets": [
                    {
                        "id": "table-1",
                        "displayName": "Customers",
                        "description": "<div>Master table</div>",
                        "multiValueAttributes": [
                            {
                                "type": {"name": "Definition"},
                                "stringValues": ["<p>Customer table definition</p>"],
                            }
                        ],
                        "outgoingRelations": [],
                        "incomingRelations": [],
                    }
                ]
            }
        if "GetColumns" in query:
            return {
                "assets": [
                    {
                        "id": "col-1",
                        "displayName": "customer_id",
                        "description": None,
                        "multiValueAttributes": [
                            {"type": {"name": "Business Name"}, "stringValues": ["Customer Key"]},
                            {"type": {"name": "Data Type"}, "stringValues": ["NUMBER(38,0)"]},
                            {"type": {"name": "Primary Key"}, "stringValues": ["true"]},
                        ],
                        "outgoingRelations": [
                            {
                                "type": {"name": "Foreign key"},
                                "target": {
                                    "id": "orders-col-1",
                                    "displayName": "CUSTOMER_ID",
                                    "type": {"name": "Column"},
                                },
                            }
                        ],
                        "incomingRelations": [],
                    },
                    {
                        "id": "col-2",
                        "displayName": "customer_name",
                        "description": "<div>Name</div>",
                        "multiValueAttributes": [
                            {"type": {"name": "Synonyms"}, "stringValues": ["Client Name", "Party Name"]},
                            {"type": {"name": "Data Type"}, "stringValues": ["VARCHAR(200)"]},
                        ],
                        "outgoingRelations": [],
                        "incomingRelations": [],
                    },
                ]
            }
        if "GetParentTable" in query:
            return {
                "assets": [
                    {
                        "incomingRelations": [
                            {
                                "source": {
                                    "id": "orders-table",
                                    "displayName": "Orders",
                                }
                            }
                        ]
                    }
                ]
            }
        raise AssertionError(f"Unexpected query {query}")


def _build_config() -> SemanticModelConfig:
    return SemanticModelConfig(
        collibra_base_url="https://example.com",
        auth_token="Bearer token",
        database="PROD_DB",
        schema="MART_CUSTOMER",
        table="DIM_CUSTOMER",
    )


def test_build_semantic_model_returns_expected_structure():
    client = FakeClient()
    model = build_semantic_model(_build_config(), client=client)

    assert model.name == "CUSTOMERS_MODEL"
    table = model.tables[0]
    assert table.name == "CUSTOMERS"
    assert table.description == "Customer table definition"
    assert table.base_table == {"database": "PROD_DB", "schema": "MART_CUSTOMER", "table": "DIM_CUSTOMER"}
    assert table.primary_key == ["CUSTOMER_ID"]

    dimensions = {dim.name: dim for dim in table.dimensions}
    assert dimensions["CUSTOMER_ID"].synonyms == ["Customer Key"]
    assert dimensions["CUSTOMER_NAME"].description == "Name"

    relationships = model.relationships
    assert relationships[0].target_table == "ORDERS"
    assert "CUSTOMERS.CUSTOMER_ID" in relationships[0].join_condition

    metrics = {metric.name: metric for metric in table.metrics}
    assert metrics["CUSTOMERS_COUNT"].expr == "COUNT(DISTINCT CUSTOMER_ID)"
    assert metrics["CUSTOMERS_ROW_COUNT"].expr == "COUNT(*)"


def test_generate_semantic_model_yaml_serializes_model():
    client = FakeClient()
    yaml_text = generate_semantic_model_yaml(_build_config(), client=client)

    assert "name: CUSTOMERS_MODEL" in yaml_text
    assert "name: CUSTOMER_ID" in yaml_text
    assert "join_condition: CUSTOMERS.CUSTOMER_ID = ORDERS.CUSTOMER_ID" in yaml_text
