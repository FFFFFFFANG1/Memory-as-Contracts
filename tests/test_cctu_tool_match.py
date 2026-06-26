from __future__ import annotations

import json
from pathlib import Path

from bench.MAC.cctu.bridge import cctu_call_function
from bench.MAC.cctu.tool_match import (
    extract_golden_inputs,
    format_did_you_mean,
    maybe_append_did_you_mean,
    rank_golden_suggestions,
)


def _load_task_codes(task_id: str) -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / "bench" / "CCTU" / "data" / "input_data.jsonl"
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        if str(row.get("id")) == task_id:
            raw = row.get("codes", {})
            return json.loads(raw) if isinstance(raw, str) else raw
    raise KeyError(task_id)


def test_format_did_you_mean_top_two_hard_cap() -> None:
    failure = "No historical event found matching the given criteria."
    one = format_did_you_mean(failure, ["keywords='alpha'"])
    two = format_did_you_mean(
        failure,
        ["keywords='alpha'", "keywords='beta'"],
    )
    assert one.endswith("Did you mean keywords='alpha' instead?")
    assert two.endswith("Did you mean keywords='alpha' or keywords='beta' instead?")


def test_task0_suggest_keywords() -> None:
    codes = _load_task_codes("0")
    code = codes["historical_event_finder"]
    goldens = extract_golden_inputs(code)
    assert any("keywords" in golden for golden in goldens)

    suggestions = rank_golden_suggestions(
        tool_name="historical_event_finder",
        arguments={"keywords": "WikiLeaks Guantanamo"},
        code=code,
        min_score=0.2,
        max_suggestions=2,
    )
    assert suggestions
    assert "wikileaks" in suggestions[0].lower()

    hinted = maybe_append_did_you_mean(
        tool_name="historical_event_finder",
        arguments={"keywords": "WikiLeaks Guantanamo"},
        code=code,
        result="No historical event found matching the given criteria.",
        min_score=0.2,
        max_suggestions=2,
    )
    assert "Did you mean" in hinted
    assert "instead?" in hinted


def test_task1_suggest_political_successor() -> None:
    codes = _load_task_codes("1")
    code = codes["political_successor_finder"]
    suggestions = rank_golden_suggestions(
        tool_name="political_successor_finder",
        arguments={
            "political_figure": "Nawaf Al-Ahmad Al-Jaber Al-Sabah",
            "role": "Emir",
            "date_of_transition": "2023-12-16",
            "country": "Kuwait",
        },
        code=code,
        min_score=0.35,
        max_suggestions=2,
    )
    assert suggestions
    assert "Emir Nawaf" in suggestions[0]

    result = cctu_call_function(
        "political_successor_finder",
        {
            "political_figure": "Nawaf Al-Ahmad Al-Jaber Al-Sabah",
            "role": "Emir",
            "date_of_transition": "2023-12-16",
            "country": "Kuwait",
        },
        code,
        match_mode="suggest",
    )
    assert "Did you mean" in result
    assert "instead?" in result
    assert "Mishal" not in result


def test_exact_mode_does_not_add_hint() -> None:
    codes = _load_task_codes("0")
    code = codes["historical_event_finder"]
    result = cctu_call_function(
        "historical_event_finder",
        {"keywords": "WikiLeaks Guantanamo"},
        code,
        match_mode="exact",
    )
    assert "Did you mean" not in result
