from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memory_as_contracts.models import ActionLogEntryV1
from memory_as_contracts.store import ContractStore


ACTION_LOG_FIELDS = {
    "seq",
    "timestamp",
    "session_id",
    "agent_id",
    "adapter_id",
    "tool_call_id",
    "tool_name",
    "host_action",
    "outcome",
    "arguments",
    "result",
    "result_text",
    "reasoning_text",
    "conversation_id",
    "turn_id",
    "user_id",
    "workspace",
    "repo",
    "branch",
    "targets",
    "risk",
    "side_effect",
}

ORDERABLE_FIELDS = {"seq", "timestamp"}
SUPPORTED_OPERATORS = {
    "eq",
    "ne",
    "in",
    "gt",
    "gte",
    "lt",
    "lte",
    "exists",
    "missing",
    "contains",
    "regex",
}


class ActionLogOrderByV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    direction: str = "asc"

    @model_validator(mode="after")
    def validate_order(self):
        if self.field not in ORDERABLE_FIELDS:
            raise ValueError(f"unsupported order_by field: {self.field}")
        if self.direction not in {"asc", "desc"}:
            raise ValueError(f"unsupported order_by direction: {self.direction}")
        return self


class ActionLogSearchSpecV1(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source: str = Field(alias="from")
    select: list[str] = Field(default_factory=lambda: sorted(ACTION_LOG_FIELDS))
    where: dict[str, dict[str, Any]] = Field(default_factory=dict)
    order_by: list[ActionLogOrderByV1] = Field(
        default_factory=lambda: [
            ActionLogOrderByV1(field="timestamp", direction="desc"),
            ActionLogOrderByV1(field="seq", direction="desc"),
        ]
    )
    limit: int

    @field_validator("source")
    @classmethod
    def source_must_be_actions(cls, value: str) -> str:
        if value != "actions":
            raise ValueError('ActionLogView.search only supports from="actions"')
        return value

    @field_validator("limit")
    @classmethod
    def limit_must_be_bounded(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("limit must be between 1 and 100")
        return value

    @model_validator(mode="after")
    def validate_virtual_fields(self):
        for field in self.select:
            if _root_field(field) not in ACTION_LOG_FIELDS:
                raise ValueError(f"unknown select field: {field}")
        for field, predicate in self.where.items():
            if _root_field(field) not in ACTION_LOG_FIELDS and field != "any_text":
                raise ValueError(f"unknown where field: {field}")
            unknown = set(predicate) - SUPPORTED_OPERATORS
            if unknown:
                raise ValueError(
                    f"unsupported operator for {field}: {sorted(unknown)[0]}"
                )
            if "in" in predicate and (
                not isinstance(predicate["in"], list) or not predicate["in"]
            ):
                raise ValueError(f"in operator for {field} requires a non-empty list")
            for operator in ("exists", "missing"):
                if operator in predicate and not isinstance(predicate[operator], bool):
                    raise ValueError(f"{operator} operator for {field} requires a boolean")
            if "regex" in predicate and not isinstance(predicate["regex"], str):
                raise ValueError(f"regex operator for {field} requires a string")
        return self


class ActionLogSearchTranslator:
    """Validate a virtual search spec and execute the bounded SQLite query."""

    def execute(
        self,
        view: "ActionLogView",
        spec: ActionLogSearchSpecV1,
    ) -> list[dict[str, Any]]:
        normalized = spec.model_dump(mode="json", by_alias=True)
        entries = view._candidate_entries(normalized)
        entries = [
            entry
            for entry in entries
            if _entry_matches(entry, normalized["where"])
        ]
        for order in reversed(normalized["order_by"]):
            reverse = order["direction"] == "desc"
            entries.sort(
                key=lambda entry: _field_value(entry, order["field"]),
                reverse=reverse,
            )
        return [
            _select_fields(entry, normalized["select"])
            for entry in entries[: normalized["limit"]]
        ]


class ActionLogView:
    """Bounded committed-action search surface exposed to validator snippets."""

    def __init__(
        self,
        store: ContractStore,
        *,
        session_id: str,
        max_limit: int = 100,
        max_candidates: int = 1000,
        translator: ActionLogSearchTranslator | None = None,
    ) -> None:
        self.store = store
        self.session_id = session_id
        self.max_limit = max_limit
        self.max_candidates = max_candidates
        self.translator = translator or ActionLogSearchTranslator()

    def search(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        validated = ActionLogSearchSpecV1.model_validate(spec)
        if validated.limit > self.max_limit:
            raise ValueError(f"limit must be between 1 and {self.max_limit}")
        return self.translator.execute(self, validated)

    def export_entries(self) -> list[dict[str, Any]]:
        """Return scoped entries for the validator sandbox worker."""
        return [entry.model_dump(mode="json") for entry in self._scoped_entries()]

    def _candidate_entries(self, normalized: dict[str, Any]) -> list[ActionLogEntryV1]:
        return self.store.search_action_log_candidates(
            session_id=self.session_id,
            where=normalized["where"],
            limit=self.max_candidates,
        )

    def _scoped_entries(self) -> list[ActionLogEntryV1]:
        entries = [
            entry
            for entry in self.store.list_action_log_entries()
            if entry.session_id == self.session_id
        ]
        return entries

def _entry_matches(entry: ActionLogEntryV1, where: dict[str, dict[str, Any]]) -> bool:
    return all(_predicate_matches(_field_value(entry, field), predicate) for field, predicate in where.items())


def _predicate_matches(value: Any, predicate: dict[str, Any]) -> bool:
    for operator, expected in predicate.items():
        if operator == "eq" and value != expected:
            return False
        if operator == "ne" and value == expected:
            return False
        if operator == "in" and value not in expected:
            return False
        if operator == "gt" and not (value is not None and value > expected):
            return False
        if operator == "gte" and not (value is not None and value >= expected):
            return False
        if operator == "lt" and not (value is not None and value < expected):
            return False
        if operator == "lte" and not (value is not None and value <= expected):
            return False
        if operator == "exists" and bool(expected) and value is None:
            return False
        if operator == "missing" and bool(expected) and value is not None:
            return False
        if operator == "contains" and str(expected) not in str(value or ""):
            return False
        if operator == "regex" and re.search(str(expected), str(value or "")) is None:
            return False
    return True


def _select_fields(entry: ActionLogEntryV1, select: list[str]) -> dict[str, Any]:
    return {field: _field_value(entry, field) for field in select}


def _field_value(entry: ActionLogEntryV1, field: str) -> Any:
    data = entry.model_dump(mode="json")
    if field == "any_text":
        return " ".join(
            str(part)
            for part in (
                data.get("tool_name"),
                data.get("host_action"),
                data.get("arguments"),
                data.get("result"),
                data.get("result_text"),
            )
            if part is not None
        )
    value: Any = data
    for part in field.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _root_field(field: str) -> str:
    return field.split(".", 1)[0]
