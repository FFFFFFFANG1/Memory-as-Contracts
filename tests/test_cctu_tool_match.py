from __future__ import annotations

import json
from pathlib import Path

from bench.MAC.cctu.bridge import cctu_call_function
from bench.MAC.cctu.tool_match import (
    extract_golden_inputs,
    format_similar_parameter_results,
    maybe_append_similar_parameter_results,
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


def _load_call_function():
    from bench.MAC.cctu.bridge import import_cctu_attr

    return import_cctu_attr("utils.utils", "call_function")


def test_format_similar_parameter_results_top_two() -> None:
    failure = "No historical event found matching the given criteria."
    formatted = format_similar_parameter_results(
        failure,
        [
            ("keywords='alpha'", "The event occurred on 2007-11-7."),
            ("keywords='beta'", "No historical event found matching the given criteria."),
        ],
    )
    assert "Similar parameter result (keywords='alpha'): The event occurred on 2007-11-7." in formatted
    assert "Similar parameter result (keywords='beta'):" in formatted
    assert "Did you mean" not in formatted


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

    hinted = maybe_append_similar_parameter_results(
        tool_name="historical_event_finder",
        arguments={"keywords": "WikiLeaks Guantanamo"},
        code=code,
        result="No historical event found matching the given criteria.",
        call_function=_load_call_function(),
        min_score=0.2,
        max_suggestions=2,
    )
    assert "Similar parameter result" in hinted
    assert "2007-11-7" in hinted
    assert "Did you mean" not in hinted


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
    assert "Similar parameter result" in result
    assert "Mishal" in result
    assert "Did you mean" not in result


def test_exact_mode_does_not_add_hint() -> None:
    codes = _load_task_codes("0")
    code = codes["historical_event_finder"]
    result = cctu_call_function(
        "historical_event_finder",
        {"keywords": "WikiLeaks Guantanamo"},
        code,
        match_mode="exact",
    )
    assert "Similar parameter result" not in result
    assert "Did you mean" not in result


def test_tool_simulator_has_datetime_in_exec_namespace() -> None:
    codes = _load_task_codes("9")
    code = codes["historical_event_finder"]
    result = cctu_call_function(
        "historical_event_finder",
        {
            "event_name": "United Nations Declaration on the Rights of Indigenous Peoples",
            "date_range": {"start_date": "2007-01-01", "end_date": "2007-12-31"},
        },
        code,
        match_mode="exact",
    )
    assert "datetime" not in result.lower() or "is not defined" not in result.lower()
    assert "an error occured" not in result.lower()


def test_task194_dict_lookup_hint() -> None:
    codes = _load_task_codes("194")
    code = codes["historical_event_retriever"]
    goldens = extract_golden_inputs(code)
    assert {"event_name": "modern state of Italy"} in goldens

    result = cctu_call_function(
        "historical_event_retriever",
        {
            "event_name": "Formation of Modern Italy",
            "event_type": "formation",
            "detail_level": "detailed",
        },
        code,
        match_mode="suggest",
    )
    assert "Similar parameter result" in result
    assert "1861" in result
    assert "Did you mean" not in result


def test_task13_for_loop_lower_and_nested_date_range_hint() -> None:
    codes = _load_task_codes("13")
    code = codes["historical_event_retriever"]
    goldens = extract_golden_inputs(code)
    assert {
        "country": "Netherlands",
        "event_type": "legalization",
        "event_name": "same-sex marriage",
        "date_range.start_date": "2001-04-01",
        "date_range.end_date": "2001-04-01",
    } in goldens

    result = cctu_call_function(
        "historical_event_retriever",
        {
            "country": "Netherlands",
            "event_type": "legalization",
            "event_name": "Legalization of same-sex marriage",
            "date_range": {"start_date": "2000-01-01", "end_date": "2001-12-31"},
        },
        code,
        match_mode="suggest",
    )
    assert "Similar parameter result" in result
    assert "2001-04-01" in result
    assert "Did you mean" not in result


def test_direct_equality_if_branch() -> None:
    codes = _load_task_codes("1")
    code = codes["historical_weather_data_retriever"]
    goldens = extract_golden_inputs(code)
    assert {"event_name": "Hurricane Otis", "date": "2023-10-25", "location": "Mexico", "parameter": "wind speed"} in goldens

    result = cctu_call_function(
        "historical_weather_data_retriever",
        {
            "event_name": "Hurricane Otis",
            "date": "2023-10-26",
            "location": "Mexico",
            "parameter": "wind speed",
            "unit": "mph",
        },
        code,
        match_mode="suggest",
    )
    assert "Similar parameter result" in result


def test_task5_tuple_dict_key_hint() -> None:
    codes = _load_task_codes("5")
    code = codes["sports_event_winner_finder"]
    goldens = extract_golden_inputs(code)
    assert {"event_name": "World Baseball Classic", "year": "2023"} in goldens

    result = cctu_call_function(
        "sports_event_winner_finder",
        {"event_name": "World Baseball Classic", "year": 2022},
        code,
        match_mode="suggest",
    )
    assert "Similar parameter result" in result
    assert "Japan" in result


def test_task24_for_loop_hint() -> None:
    codes = _load_task_codes("24")
    code = codes["diplomatic_event_finder"]
    goldens = extract_golden_inputs(code)
    assert any(
        golden.get("event_type") == "expulsion"
        and golden.get("person_name") == "Daniel Kriener"
        and golden.get("date") == "2019-03-06"
        for golden in goldens
    )

    result = cctu_call_function(
        "diplomatic_event_finder",
        {
            "event_type": "expulsion",
            "person_name": "Daniel Kriener",
            "date": "2019-03-07",
        },
        code,
        match_mode="suggest",
    )
    assert "Similar parameter result" in result
    assert "Daniel Kriener" in result


def test_task46_stub_non_direct_match_returns_hint_not_stub() -> None:
    codes = _load_task_codes("46")
    code = codes["corporate_event_tracker"]
    result = cctu_call_function(
        "corporate_event_tracker",
        {
            "company_name": "Centura Health",
            "event_type": "split",
            "event_date": "2023-08-01",
        },
        code,
        match_mode="suggest",
    )
    assert "retrieved successfully" not in result.lower()
    assert "Similar parameter result" in result
    assert "August 2023" in result
    assert "AdventHealth" in result


def test_task0_for_loop_golden() -> None:
    codes = _load_task_codes("0")
    code = codes["political_event_tracker"]
    goldens = extract_golden_inputs(code)
    assert {
        "person": "Olaf Scholz",
        "event_type": "dismissal",
        "year": "2024",
        "country": "Germany",
    } in goldens
