from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memory_as_contracts.action_log import ActionLogView
from memory_as_contracts.models import ActionLogEntryV1, ActionOutcome
from memory_as_contracts.store import ContractStore


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


def committed_action(tool_call_id: str = "call-1") -> ActionLogEntryV1:
    return ActionLogEntryV1(
        adapter_id="codex",
        session_id="sess-1",
        task_id="task-1",
        agent_id="codex",
        tool_call_id=tool_call_id,
        tool_name="Bash",
        host_action="exec",
        arguments={"command": "pytest"},
        result={"exit_code": 0},
        result_text="1 passed",
        outcome=ActionOutcome.SUCCESS,
        timestamp=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
    )


def test_action_log_append_is_idempotent_and_assigns_commit_order() -> None:
    store = make_store()

    first = store.add_action_log_entry(committed_action())
    duplicate = store.add_action_log_entry(committed_action())
    with pytest.raises(ValueError, match="idempotency"):
        store.add_action_log_entry(
            committed_action().model_copy(update={"result_text": "conflicting payload"})
        )

    entries = store.list_action_log_entries()
    assert first.seq == 1
    assert duplicate.seq == first.seq
    assert len(entries) == 1
    assert entries[0].seq == 1
    assert entries[0].result_text == "1 passed"


def test_action_log_view_search_validates_and_queries_bounded_specs() -> None:
    store = make_store()
    store.add_action_log_entry(committed_action("call-1"))
    store.add_action_log_entry(
        committed_action("call-2").model_copy(
            update={
                "arguments": {"command": "npm test"},
                "outcome": ActionOutcome.FAILURE,
                "result_text": "failed",
            }
        )
    )
    store.add_action_log_entry(
        committed_action("call-3").model_copy(
            update={"session_id": "other-session", "arguments": {"command": "pytest"}}
        )
    )
    view = ActionLogView(store, session_id="sess-1", task_id="task-1")

    rows = view.search(
        {
            "from": "actions",
            "select": ["seq", "tool_name", "arguments", "result_text"],
            "where": {
                "tool_name": {"in": ["Bash"]},
                "outcome": {"eq": "success"},
                "arguments.command": {"regex": "^pytest$"},
            },
            "order_by": [{"field": "seq", "direction": "asc"}],
            "limit": 10,
        }
    )

    assert rows == [
        {
            "seq": 1,
            "tool_name": "Bash",
            "arguments": {"command": "pytest"},
            "result_text": "1 passed",
        }
    ]
    with pytest.raises(ValueError, match="limit"):
        view.search({"from": "actions", "select": ["seq"], "where": {"tool_name": {"eq": "Bash"}}})
    with pytest.raises(ValueError, match="unknown select field"):
        view.search({"from": "actions", "select": ["sqlite_rowid"], "where": {}, "limit": 5})


def test_action_log_search_defaults_to_most_recent_actions_first() -> None:
    store = make_store()
    store.add_action_log_entry(committed_action("call-1"))
    store.add_action_log_entry(committed_action("call-2"))
    view = ActionLogView(store, session_id="sess-1", task_id="task-1")

    rows = view.search(
        {
            "from": "actions",
            "select": ["seq", "tool_call_id"],
            "where": {},
            "limit": 2,
        }
    )

    assert rows == [
        {"seq": 2, "tool_call_id": "call-2"},
        {"seq": 1, "tool_call_id": "call-1"},
    ]


def test_action_log_parent_limits_recent_candidates_before_python_filtering() -> None:
    store = make_store()
    store.add_action_log_entry(
        committed_action("call-1").model_copy(
            update={"arguments": {"command": "old-match"}}
        )
    )
    store.add_action_log_entry(
        committed_action("call-2").model_copy(
            update={"arguments": {"command": "recent-one"}}
        )
    )
    store.add_action_log_entry(
        committed_action("call-3").model_copy(
            update={"arguments": {"command": "recent-two"}}
        )
    )
    view = ActionLogView(
        store,
        session_id="sess-1",
        task_id="task-1",
        max_candidates=2,
    )

    rows = view.search(
        {
            "from": "actions",
            "select": ["seq"],
            "where": {"arguments.command": {"regex": "^old-match$"}},
            "limit": 10,
        }
    )

    assert rows == []


def test_action_log_view_uses_store_search_interface_without_sqlite_access() -> None:
    entry = committed_action().model_copy(update={"seq": 1})

    class SearchOnlyStore:
        def search_action_log_candidates(
            self,
            *,
            session_id,
            task_id,
            where,
            limit,
        ):
            assert session_id == "sess-1"
            assert task_id == "task-1"
            assert where == {"tool_name": {"eq": "Bash"}}
            assert limit == 1000
            return [entry]

    view = ActionLogView(
        SearchOnlyStore(),
        session_id="sess-1",
        task_id="task-1",
    )

    rows = view.search(
        {
            "from": "actions",
            "select": ["tool_name", "tool_call_id"],
            "where": {"tool_name": {"eq": "Bash"}},
            "limit": 5,
        }
    )

    assert rows == [{"tool_name": "Bash", "tool_call_id": "call-1"}]
