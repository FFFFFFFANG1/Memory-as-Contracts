from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ContractType(StrEnum):
    PROHIBITION = "prohibition"
    REQUIREMENT = "requirement"
    PROCEDURE = "procedure"
    PREFERENCE = "preference"
    EXCEPTION = "exception"
    FACT = "fact"


class Modality(StrEnum):
    MUST = "MUST"
    MUST_NOT = "MUST_NOT"
    SHOULD = "SHOULD"
    MAY = "MAY"


class SourceKind(StrEnum):
    USER_EXPLICIT = "user_explicit"
    PROJECT_DOC = "project_doc"
    TOOL_OBSERVATION = "tool_observation"
    AGENT_INFERRED = "agent_inferred"


class ScopeLevel(StrEnum):
    PROJECT = "project"
    FOLDER = "folder"
    FILE = "file"
    SESSION = "session"
    TASK = "task"


class Strength(StrEnum):
    HARD = "hard"
    SOFT = "soft"
    SUGGESTIVE = "suggestive"


class ContractStatus(StrEnum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    PENDING_CONFLICT = "pending_conflict"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ActionClass(StrEnum):
    EDIT_FILE = "edit_file"
    DELETE_FILE = "delete_file"
    RUN_COMMAND = "run_command"
    FORMAT_FILE = "format_file"
    INSTALL_DEPENDENCY = "install_dependency"
    COMMIT = "commit"
    PUSH = "push"
    UPDATE_DOCS = "update_docs"


class GateDecisionType(StrEnum):
    ALLOW = "allow"
    REVISE = "revise"
    CONFIRM = "confirm"
    BLOCK = "block"
    DEFER = "defer"


class Source(BaseModel):
    kind: SourceKind
    span: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    path: str | None = None
    fingerprint: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Scope(BaseModel):
    workspace: str = "default"
    path_globs: list[str] = Field(default_factory=list)
    task: str | None = None
    level: ScopeLevel = ScopeLevel.PROJECT


class Validity(BaseModel):
    starts_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None


class Contract(BaseModel):
    id: str = Field(default_factory=lambda: f"C-{uuid4().hex[:8]}")
    text: str
    type: ContractType
    modality: Modality
    source: Source
    scope: Scope = Field(default_factory=Scope)
    action_classes: list[ActionClass] = Field(default_factory=list)
    validity: Validity = Field(default_factory=Validity)
    strength: Strength = Strength.SOFT
    confirmation: Literal["not_required", "required", "required_to_override"] = "not_required"
    status: ContractStatus = ContractStatus.ACTIVE
    supersedes: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("action_classes")
    @classmethod
    def fact_cannot_authorize_actions(
        cls, action_classes: list[ActionClass], info: Any
    ) -> list[ActionClass]:
        if info.data.get("type") == ContractType.FACT and action_classes:
            raise ValueError("fact contracts cannot directly bind action classes")
        return action_classes

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.validity.expires_at is None:
            return False
        check_time = now or datetime.now(timezone.utc)
        return self.validity.expires_at <= check_time


class ActionSignature(BaseModel):
    action_class: ActionClass
    target: str | None = None
    cwd: str | None = None
    risk: Literal["low", "medium", "high"] = "medium"
    intent: str = ""


class GateDecision(BaseModel):
    decision: GateDecisionType
    reason: str
    applicable_contracts: list[str] = Field(default_factory=list)
    allowed_override: str | None = None


class InfluenceReceipt(BaseModel):
    id: str = Field(default_factory=lambda: f"R-{uuid4().hex[:8]}")
    action_id: str = Field(default_factory=lambda: f"A-{uuid4().hex[:8]}")
    action_class: ActionClass
    target: str | None = None
    decision: GateDecisionType
    contracts_used: list[str] = Field(default_factory=list)
    contracts_ignored: list[dict[str, str]] = Field(default_factory=list)
    result: str = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContractEdgeType(StrEnum):
    CONFLICTS_WITH = "conflicts_with"
    SUPERSEDES = "supersedes"
    REJECTED_BY = "rejected_by"


class ContractEdge(BaseModel):
    id: str = Field(default_factory=lambda: f"E-{uuid4().hex[:8]}")
    source_contract_id: str
    target_contract_id: str
    relation: ContractEdgeType
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceSnapshot(BaseModel):
    source_key: str
    adapter: str
    path: str
    workspace: str
    source_kind: SourceKind
    fingerprint: str
    content: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
