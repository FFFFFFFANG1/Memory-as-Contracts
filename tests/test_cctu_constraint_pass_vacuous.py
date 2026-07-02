from __future__ import annotations

from bench.MAC.cctu.grade_answer import grade_one


def test_constraint_pass_true_when_no_required_tool_slots() -> None:
    row = {
        "task_uid": "mac-cctu-t-00000",
        "events": [
            {
                "event": "tool_result",
                "name": "send_message",
                "terminal": True,
                "result": {"ok": True, "terminal": True},
            }
        ],
        "final_answer": "final answer text",
        "stop_reason": "send_message",
    }
    task = {
        "cctu_id": "0",
        "cctu_sample": {
            "id": "0_0",
            "answer": "final answer text",
            "unsolved_set": "{}",
            "constraints_list": [],
            "messages": [],
            "tools": "[]",
        },
    }
    grade = grade_one(row, task, samples={})

    assert grade["acc"] is True
    assert grade["constraint_pass"] is True
    assert grade["constraint_total"] == 0
    assert grade["constraint_satisfied"] == 0
    assert grade["constraint_violation_rate"] == 0.0
    assert grade["unsolved_slot_total"] == 0
    assert grade["step_pass_rate"] == 1.0
    assert grade["joint_pass"] is grade["answer_pass"]


def test_constraint_pass_false_when_any_constraints_list_rule_violated(monkeypatch) -> None:
    row = {
        "task_uid": "mac-cctu-t-00000",
        "events": [
            {
                "event": "tool_result",
                "name": "send_message",
                "terminal": True,
                "result": {"ok": True, "terminal": True},
            }
        ],
        "final_answer": "final answer text",
        "stop_reason": "send_message",
    }
    task = {
        "cctu_id": "0",
        "cctu_sample": {
            "id": "0_0",
            "answer": "final answer text",
            "unsolved_set": "{}",
            "constraints_list": [["Response", "Format", "must use a table"]],
            "messages": [],
            "tools": "[]",
        },
    }

    def fake_replay(_messages, _sample):
        return [{"message_index": 0, "content": "violation"}], {0}, 2

    monkeypatch.setattr(
        "bench.MAC.cctu.grade_answer.replay_constraint_analysis",
        fake_replay,
    )
    grade = grade_one(row, task, samples={})

    assert grade["constraint_total"] == 2
    assert grade["constraint_satisfied"] == 1
    assert grade["constraint_violation_rate"] == 0.5
    assert grade["constraint_pass"] is False
    assert grade["has_last_if_error"] is False
