from __future__ import annotations

from bench.MAC.cctu.grade_answer import grade_one


def test_answer_pass_uses_final_text_only_unsolved_slots_are_step_success() -> None:
    row = {
        "task_uid": "mac-cctu-t-00000",
        "events": [
            {
                "event": "model_response",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_hist",
                        "name": "historical_event_finder",
                        "arguments": {},
                    }
                ],
            },
            {
                "event": "tool_result",
                "tool_call_id": "call_hist",
                "name": "historical_event_finder",
                "arguments": {},
                "result": "wrong intermediate value",
            },
            {
                "event": "tool_result",
                "name": "send_message",
                "terminal": True,
                "result": {"ok": True, "terminal": True},
            },
        ],
        "final_answer": "2007-11-7",
        "stop_reason": "send_message",
    }
    task = {
        "cctu_id": "0",
        "cctu_sample": {
            "id": "0_0",
            "answer": "2007-11-7",
            "unsolved_set": '{"historical_event_finder": ["2007-11-7"]}',
            "constraints_list": [],
            "messages": [],
            "tools": "[]",
        },
    }
    grade = grade_one(row, task, samples={})

    assert grade["answer_text_pass"] is True
    assert grade["answer_data_pass"] is False
    assert grade["acc"] is False
    assert grade["answer_pass"] is True
    assert grade["step_pass_rate"] == 0.0
    assert grade["constraint_pass"] is True
    assert grade["joint_pass"] is True


def test_answer_pass_true_when_text_and_unsolved_slots_match() -> None:
    row = {
        "task_uid": "mac-cctu-t-00000",
        "events": [
            {
                "event": "model_response",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_hist",
                        "name": "historical_event_finder",
                        "arguments": {},
                    }
                ],
            },
            {
                "event": "tool_result",
                "tool_call_id": "call_hist",
                "name": "historical_event_finder",
                "arguments": {},
                "result": "The date is 2007-11-7",
            },
            {
                "event": "tool_result",
                "name": "send_message",
                "terminal": True,
                "result": {"ok": True, "terminal": True},
            },
        ],
        "final_answer": "2007-11-7",
        "stop_reason": "send_message",
    }
    task = {
        "cctu_id": "0",
        "cctu_sample": {
            "id": "0_0",
            "answer": "2007-11-7",
            "unsolved_set": '{"historical_event_finder": ["2007-11-7"]}',
            "constraints_list": [],
            "messages": [],
            "tools": "[]",
        },
    }
    grade = grade_one(row, task, samples={})

    assert grade["answer_text_pass"] is True
    assert grade["answer_data_pass"] is True
    assert grade["answer_pass"] is True
    assert grade["constraint_pass"] is True
    assert grade["joint_pass"] is True
