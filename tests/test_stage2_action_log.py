from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from memory_as_contracts.action_log import ActionLogView
from memory_as_contracts.models import ActionLogEntryV1, ActionOutcome
from memory_as_contracts.store import ContractStore


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


def test_action_log_migration_removes_task_and_organization_columns(tmp_path) -> None:
    db_path = tmp_path / "mac.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version(version) VALUES (9);
        CREATE TABLE action_log (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            adapter_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            task_id TEXT,
            agent_id TEXT NOT NULL,
            tool_call_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            host_action TEXT NOT NULL,
            arguments_json TEXT NOT NULL,
            result_json TEXT,
            result_text TEXT NOT NULL,
            outcome TEXT NOT NULL,
            reasoning_text TEXT,
            conversation_id TEXT,
            turn_id TEXT,
            user_id TEXT,
            organization TEXT,
            workspace TEXT,
            repo TEXT,
            branch TEXT,
            targets_json TEXT NOT NULL DEFAULT '[]',
            risk TEXT NOT NULL DEFAULT 'medium',
            side_effect TEXT NOT NULL DEFAULT 'none',
            timestamp TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(adapter_id, session_id, tool_call_id)
        );
        """
    )
    conn.execute(
        """
        INSERT INTO action_log (
            adapter_id, session_id, task_id, agent_id, tool_call_id,
            tool_name, host_action, arguments_json, result_text, outcome,
            organization, targets_json, risk, side_effect, timestamp, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "codex",
            "sess-1",
            "task-1",
            "codex",
            "call-1",
            "Bash",
            "exec",
            json.dumps({"command": "pytest"}),
            "1 passed",
            "success",
            "org-1",
            "[]",
            "medium",
            "none",
            "2026-06-06T12:00:00+00:00",
            json.dumps({"session_id": "sess-1", "task_id": "task-1", "organization": "org-1"}),
        ),
    )
    conn.commit()
    conn.close()

    store = ContractStore(db_path)
    store.init_db()
    store.close()

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(action_log)").fetchall()}
    payload = json.loads(conn.execute("SELECT payload_json FROM action_log").fetchone()[0])
    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    conn.close()

    assert version == 12
    assert "task_id" not in columns
    assert "organization" not in columns
    assert "task_id" not in payload
    assert "organization" not in payload


def committed_action(tool_call_id: str = "call-1") -> ActionLogEntryV1:
    return ActionLogEntryV1(
        adapter_id="codex",
        session_id="sess-1",
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


def test_action_log_entry_rejects_task_and_organization_scope_fields() -> None:
    with pytest.raises(ValueError):
        ActionLogEntryV1(
            adapter_id="codex",
            session_id="sess-1",
            task_id="task-1",
            organization="org-1",
            agent_id="codex",
            tool_call_id="call-1",
            tool_name="Bash",
            host_action="exec",
            arguments={"command": "pytest"},
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
    view = ActionLogView(store, session_id="sess-1")

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
    view = ActionLogView(store, session_id="sess-1")

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
            where,
            limit,
        ):
            assert session_id == "sess-1"
            assert where == {"tool_name": {"eq": "Bash"}}
            assert limit == 1000
            return [entry]

    view = ActionLogView(
        SearchOnlyStore(),
        session_id="sess-1",
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
