from bench.MAC.cctu.audit_tool_schema import audit_tool_pair
from bench.MAC.cctu.tool_match import format_cctu_call_error


def test_sim_required_missing_from_schema_required():
    code = """
def historical_event_retriever(country, event_type, event_name, date_range):
    return country
"""
    schema = {
        "type": "object",
        "properties": {
            "country": {"type": "string"},
            "event_type": {"type": "string"},
            "event_name": {"type": "string"},
            "date_range": {"type": "object"},
        },
        "required": ["country", "event_type", "event_name"],
    }
    issues = audit_tool_pair(task_id="0", tool_name="historical_event_retriever", schema=schema, code=code)
    kinds = {issue.kind for issue in issues}
    assert "sim_required_not_in_schema_required" in kinds
    assert any(issue.param == "date_range" for issue in issues)


def test_schema_prop_not_in_sim():
    code = """
def lookup(keywords):
    return keywords
"""
    schema = {
        "type": "object",
        "properties": {
            "keywords": {"type": "string"},
            "topic": {"type": "string"},
        },
        "required": ["keywords"],
    }
    issues = audit_tool_pair(task_id="0", tool_name="lookup", schema=schema, code=code)
    assert any(issue.kind == "schema_prop_not_in_sim" and issue.param == "topic" for issue in issues)


def test_format_cctu_call_error_keeps_original_prefix():
    formatted = format_cctu_call_error(
        tool_name="demo_tool",
        arguments={"a": 1},
        code="def demo_tool(a, b):\n    return a\n",
        exc=TypeError("demo_tool() missing 1 required positional argument: 'b'"),
        schema={"properties": {"b": {"type": "string", "enum": ["x", "y"]}}, "required": ["a", "b"]},
    )
    assert formatted.startswith("an error occured when call demo_tool:")
    assert "Missing required parameter(s): b." in formatted
    assert 'allowed values: ["x", "y"]' in formatted
