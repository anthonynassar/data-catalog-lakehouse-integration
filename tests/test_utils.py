from collibra_semantic_model.utils import coalesce_first, normalize_synonyms, strip_html


def test_strip_html_removes_tags_and_whitespace():
    html_text = "<div>Hello <strong>World</strong>&nbsp;</div>"
    assert strip_html(html_text) == "Hello World"


def test_normalize_synonyms_deduplicates_case_insensitive():
    values = ["Customer", "customer", "  Client  ", ""]
    assert normalize_synonyms(values) == ["Client", "Customer"]


def test_coalesce_first_returns_first_non_empty():
    assert coalesce_first("", [""], "Candidate") == "Candidate"
    assert coalesce_first(None, []) == ""
