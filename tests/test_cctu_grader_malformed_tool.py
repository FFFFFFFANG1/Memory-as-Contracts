from __future__ import annotations

import pytest

from bench.MAC.cctu.bridge import build_cctu_eval_task
from bench.MAC.cctu.grade_answer import grade_one


@pytest.mark.parametrize(
    "malformed_name",
    [
        "historical_event_data_retriever eventdata_format</arg_key><arg_value>JSON</arg_value>",
        "artwork_information_retriever.artist_name</arg_key><arg_value>Tiepolo</arg_value>",
    ],
)
def test_grade_one_treats_malformed_tool_name_as_invalid_action(malformed_name: str) -> None:
    task = build_cctu_eval_task("mac-cctu-t-00018")
    row = {
        "task_uid": task["task_uid"],
        "events": [
            {
                "event": "model_response",
                "content": "",
                "tool_calls": [
                    {"id": "bad-call", "name": malformed_name, "arguments": {}}
                ],
            },
            {
                "event": "tool_result",
                "tool_call_id": "bad-call",
                "name": malformed_name,
                "arguments": {},
                "result": f"Unknown CCTU tool: {malformed_name}",
            },
        ],
        "final_answer": None,
        "stop_reason": "max_iterations",
    }

    grade = grade_one(row, task, samples={})

    assert grade["task_uid"] == task["task_uid"]
    assert grade["answer_pass"] is False
    assert grade["constraint_total"] == len(task["constraints_list"])
