from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Decision = Literal["allow", "reject", "ask"]
Modality = Literal["must", "must_not", "may", "prefer", "ask_before"]
Directness = Literal["embedded", "direct"]
EdgeType = Literal[
    "exception_to",
    "overrides",
    "supersedes",
    "refines",
    "conflicts_with",
    "independent",
]
ActionFamily = Literal[
    "code.read",
    "code.edit",
    "code.delete",
    "test.run",
    "dependency.add",
    "command.execute",
    "git.commit",
    "git.push",
    "user.ask",
    "record.read",
    "record.create",
    "record.update",
    "record.delete",
    "message.send",
    "information.disclose",
    "booking.create",
    "booking.cancel",
    "payment.charge",
    "refund.issue",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionPredicate(StrictModel):
    family: ActionFamily
    object: str | None = None
    target: str | None = None
    effect: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class Lifecycle(StrictModel):
    effective_from_event: int = Field(ge=0)
    effective_until_event: int | None = Field(default=None, ge=0)
    until_revoked: bool = True
    revoked_at_event: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> "Lifecycle":
        if (
            self.effective_until_event is not None
            and self.effective_until_event < self.effective_from_event
        ):
            raise ValueError("effective_until_event must be >= effective_from_event")
        if self.revoked_at_event is not None and self.revoked_at_event < self.effective_from_event:
            raise ValueError("revoked_at_event must be >= effective_from_event")
        return self


class ContractNode(StrictModel):
    id: str
    surface_text: str
    modality: Modality
    action_predicate: ActionPredicate
    scope: dict[str, Any] = Field(default_factory=dict)
    lifecycle: Lifecycle
    source_turn_ids: list[str]
    directness: Directness = "embedded"
    authority: int = 0
    blueprint_id: str | None = None

    @field_validator("source_turn_ids")
    @classmethod
    def require_source_turn(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("source_turn_ids must not be empty")
        return value


class ContractEdge(StrictModel):
    id: str
    type: EdgeType
    source: str
    target: str
    surface_text: str | None = None


class ContractGraph(StrictModel):
    graph_id: str
    nodes: list[ContractNode]
    edges: list[ContractEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "ContractGraph":
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("contract node ids must be unique")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known:
                raise ValueError(f"edge {edge.id} has unknown source {edge.source}")
            if edge.target not in known:
                raise ValueError(f"edge {edge.id} has unknown target {edge.target}")
        return self


class CanonicalAction(StrictModel):
    family: ActionFamily
    tool: str | None = None
    target: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    effect_summary: str
    object: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)


class CanonicalEvent(StrictModel):
    event_id: int = Field(ge=0)
    turn_id: str
    timestamp: str | None = None
    role: Literal["system", "user", "assistant", "tool", "project", "maintainer", "policy"]
    content: str = ""
    action: CanonicalAction | None = None
    observation: dict[str, Any] = Field(default_factory=dict)
    state_summary: dict[str, Any] = Field(default_factory=dict)
    source: str


class HistoryPack(StrictModel):
    history_id: str
    source: str
    source_task_id: str
    source_revision: str
    events: list[CanonicalEvent]
    contract_graph: ContractGraph | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_events(self) -> "HistoryPack":
        ids = [event.event_id for event in self.events]
        if ids != sorted(ids):
            raise ValueError("events must be sorted by event_id")
        if len(set(ids)) != len(ids):
            raise ValueError("event_id values must be unique")
        return self


class GoldLabel(StrictModel):
    decision: Decision
    active_contract_ids: list[str] = Field(default_factory=list)
    decisive_relation_ids: list[str] = Field(default_factory=list)


class QAMetadata(StrictModel):
    trajectory_progress: float = Field(ge=0.0, le=1.0)
    prefix_tokens: int = Field(ge=0)
    evidence_distance_tokens: int = Field(ge=0)
    intervening_contract_events: int = Field(ge=0)
    variant_type: str


class QAItem(StrictModel):
    qa_id: str
    track: Literal["coding", "general"]
    source: Literal["scbench", "swebench_verified", "toolsandbox", "tau"]
    trajectory_id: str
    prefix_end_event: int = Field(ge=0)
    history_prefix_ref: str
    current_context: dict[str, Any]
    proposed_action: CanonicalAction
    gold: GoldLabel
    evidence_turn_ids: list[str]
    probe_metadata: QAMetadata
    event_group_id: str | None = None
    split: Literal["development", "public_test", "hidden_test"] | None = None

    @field_validator("evidence_turn_ids")
    @classmethod
    def require_evidence(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("evidence_turn_ids must not be empty")
        return value
