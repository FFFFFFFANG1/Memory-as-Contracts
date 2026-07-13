"""Audited MAC-side repairs for retained CCTU task carriers.

The vendored CCTU checkout remains unchanged.  These overlays make a small set
of retained, otherwise-simple tasks reachable without requiring the agent to
guess an answer-bearing date parameter before calling the tool.
"""

from __future__ import annotations

import copy
from typing import Any


EXCLUDED_TASK_UIDS = frozenset(
    {
        "mac-cctu-t-00055",
        "mac-cctu-t-00057",
        "mac-cctu-t-00060",
        "mac-cctu-t-00066",
        "mac-cctu-t-00085",
        "mac-cctu-t-00086",
        "mac-cctu-t-00088",
        "mac-cctu-t-00094",
        "mac-cctu-t-00158",
        "mac-cctu-t-00161",
        "mac-cctu-t-00165",
        "mac-cctu-t-00169",
        "mac-cctu-t-00171",
        "mac-cctu-t-00176",
        "mac-cctu-t-00179",
        "mac-cctu-t-00182",
    }
)

ANSWER_OVERRIDES = {
    # Previously audited answer aliases. Keep these in the MAC-side source of
    # truth instead of relying on the nested CCTU snapshot: the grader overlays
    # the task-level answer onto that snapshot.
    "mac-cctu-t-00101": "35 or 30",
    "mac-cctu-t-00113": "The start of Billy Graham's Los Angeles Crusade or Billy Graham",
    "mac-cctu-t-00123": "54 or 44",
    "mac-cctu-t-00133": "16,000 or 12,000, 4,000",
    "mac-cctu-t-00135": "30,002 or 2, 30,000",
    "mac-cctu-t-00145": "5 or 3, 2",
    "mac-cctu-t-00159": "no or false",
    "mac-cctu-t-00191": "no or false",
    # Keep all audited answer repairs in the same backward-compatible
    # ``old or repaired`` form used by the earlier CCTU patches.
    "mac-cctu-t-00111": "3 or 33",
    "mac-cctu-t-00137": "6 or 8",
}

_OPTIONAL_TOOL_ARGUMENTS = {
    ("mac-cctu-t-00015", "historical_event_finder"): {"date_range"},
    ("mac-cctu-t-00048", "historical_event_locator"): {"date"},
}

_CODE_OVERRIDES = {
    (
        "mac-cctu-t-00009",
        "historical_event_finder",
    ): '''def historical_event_finder(event_name, organization=None, event_type=None, include_context=False, date_range=None, location=None):
    query = f"{organization or ''} {event_name or ''}".lower()
    required = ("united nations", "declaration", "rights of indigenous peoples")
    if all(term in query for term in required):
        response = "2007-09-13"
        if include_context:
            response += " - The United Nations General Assembly adopted the declaration."
        return response
    return "Error: Event not found."
''',
    (
        "mac-cctu-t-00015",
        "historical_event_finder",
    ): '''def historical_event_finder(event_description, date_range=None, region=None, source_type="news", event_type="political", significance_level="national"):
    query = (event_description or "").lower()
    required = ("henri", "guillaume", "royal duties")
    if all(term in query for term in required):
        return "The event occurred on 2024-6-23."
    return "No matching historical event found within the specified parameters."
''',
    (
        "mac-cctu-t-00048",
        "historical_event_locator",
    ): '''def historical_event_locator(event_name, date=None, involved_parties=None, event_type=None, contextual_info=False, location=None, significance=None, source_reliability=None):
    query = (event_name or "").lower()
    required = ("north korea", "united states", "summit")
    if not all(term in query for term in required):
        return {"error": "Event not found in the database."}
    return {
        "location": "Hanoi",
        "date": date or "2019-02-27",
        "involved_parties": involved_parties or ["North Korea", "United States"],
        "event_type": event_type or "summit",
        "contextual_info": contextual_info,
        "significance": significance or "high",
        "source_reliability": source_reliability or "verified",
    }
''',
}


def repaired_answer(task_uid: str, answer: Any) -> Any:
    return ANSWER_OVERRIDES.get(task_uid, answer)


def repair_tool_schemas(task_uid: str, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repaired = copy.deepcopy(tools)
    for tool in repaired:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = fn.get("name")
        optional = _OPTIONAL_TOOL_ARGUMENTS.get((task_uid, str(name)))
        parameters = fn.get("parameters") if isinstance(fn, dict) else None
        if not isinstance(parameters, dict) and isinstance(fn, dict):
            parameters = fn.get("input_schema")
        if not optional or not isinstance(parameters, dict):
            continue
        required = parameters.get("required")
        if isinstance(required, list):
            parameters["required"] = [field for field in required if field not in optional]
    return repaired


def repair_tool_codes(task_uid: str, codes: dict[str, str]) -> dict[str, str]:
    repaired = dict(codes)
    for (repair_uid, tool_name), code in _CODE_OVERRIDES.items():
        if repair_uid == task_uid:
            repaired[tool_name] = code
    return repaired
