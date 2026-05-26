from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def prefixed_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContractKind(StrEnum):
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


class Strength(StrEnum):
    HARD = "hard"
    SOFT = "soft"
    SUGGESTIVE = "suggestive"


class SourceKind(StrEnum):
    USER_TURN = "user_turn"
    PROJECT_DOC = "project_doc"
    MEMORY_FILE = "memory_file"
    USER_PROFILE = "user_profile"
    TOOL_OBSERVATION = "tool_observation"
    AGENT_INFERRED = "agent_inferred"


class ScopeLevel(StrEnum):
    PER_TURN = "per_turn"
    TASK = "task"
    SESSION = "session"
    COMPONENT = "component"
    PROJECT = "project"
    REPO = "repo"
    PATH = "path"
    AGENT_FAMILY = "agent_family"
    ORGANIZATION = "organization"
    GLOBAL = "global"


class LifecycleType(StrEnum):
    IMMEDIATE = "immediate"
    BOUNDED_TIME = "bounded_time"
    BOUNDED_SESSION = "bounded_session"
    BOUNDED_TASK = "bounded_task"
    UNTIL_REVOKED = "until_revoked"
    CONDITIONAL = "conditional"
    REVIEW_AFTER = "review_after"


class ContractStatus(StrEnum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    PENDING_CONFLICT = "pending_conflict"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    EXPIRED = "expired"
    INACTIVE = "inactive"


class EdgeRelation(StrEnum):
    DUPLICATE = "duplicate"
    REFINEMENT = "refinement"
    SUPERSEDES = "supersedes"
    CONFLICTS_WITH = "conflicts_with"
    EXCEPTION_TO = "exception_to"
    OVERRIDE = "override"
    INDEPENDENT = "independent"


class PredicateStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GateDecisionType(StrEnum):
    ALLOW = "allow"
    REVISE = "revise"
    CONFIRM = "confirm"
    BLOCK = "block"
    DEFER = "defer"


class MatchOutcome(StrEnum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    AMBIGUOUS = "ambiguous"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SideEffect(StrEnum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXTERNAL_WRITE = "external_write"


class OverrideRequirement(StrEnum):
    NONE = "none"
    EXPLICIT_USER_CONFIRMATION = "explicit_user_confirmation"


class ContractSource(StrictModel):
    kind: SourceKind
    span: str
    created_at: datetime = Field(default_factory=utc_now)
    conversation_id: str | None = None
    turn_id: str | None = None
    path: str | None = None
    fingerprint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("created_at")
    @classmethod
    def created_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class Scope(StrictModel):
    level: ScopeLevel
    workspace: str | None = None
    repo: str | None = None
    path_globs: list[str] = Field(default_factory=list)
    task: str | None = None
    component: str | None = None
    agent_family: list[str] = Field(default_factory=list)
    organization: str | None = None
    user_id: str | None = None

    @model_validator(mode="after")
    def validate_scope_boundary(self) -> Self:
        if self.level == ScopeLevel.PATH and not self.path_globs:
            raise ValueError("path scope requires at least one path_glob")
        if self.level == ScopeLevel.REPO and not (self.repo or self.workspace):
            raise ValueError("repo scope requires repo or workspace")
        if self.level == ScopeLevel.PROJECT and not self.workspace:
            raise ValueError("project scope requires workspace")
        if self.level == ScopeLevel.TASK and not self.task:
            raise ValueError("task scope requires task")
        if self.level == ScopeLevel.COMPONENT and not self.component:
            raise ValueError("component scope requires component")
        if self.level == ScopeLevel.AGENT_FAMILY and not self.agent_family:
            raise ValueError("agent_family scope requires at least one agent family")
        if self.level == ScopeLevel.ORGANIZATION and not self.organization:
            raise ValueError("organization scope requires organization")
        return self


class Lifecycle(StrictModel):
    type: LifecycleType = LifecycleType.IMMEDIATE
    effective_from: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    until_revoked: bool = False
    trigger_event: str | None = None
    review_after: datetime | None = None
    original_text: str | None = None

    @field_validator("effective_from", "expires_at", "review_after")
    @classmethod
    def lifecycle_times_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("lifecycle timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_lifecycle_boundary(self) -> Self:
        if self.expires_at is not None and self.expires_at <= self.effective_from:
            raise ValueError("expires_at must be after effective_from")
        if self.type == LifecycleType.BOUNDED_TIME and self.expires_at is None:
            raise ValueError("bounded_time lifecycle requires expires_at")
        if self.type == LifecycleType.UNTIL_REVOKED and not self.until_revoked:
            raise ValueError("until_revoked lifecycle requires until_revoked=true")
        if self.type == LifecycleType.UNTIL_REVOKED and self.expires_at is not None:
            raise ValueError("until_revoked lifecycle cannot also have expires_at")
        if self.type == LifecycleType.CONDITIONAL and not self.trigger_event:
            raise ValueError("conditional lifecycle requires trigger_event")
        if self.type == LifecycleType.REVIEW_AFTER and self.review_after is None:
            raise ValueError("review_after lifecycle requires review_after")
        return self

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        check_time = now or utc_now()
        return self.expires_at <= check_time


class ActionConstraints(StrictModel):
    host_actions: list[str] = Field(default_factory=list)
    canonical_tags: list[str] = Field(default_factory=list)


class HostActionPattern(StrictModel):
    action: str
    tool_name: str | None = None
    program: str | None = None
    subcommand: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    parameter_regex: dict[str, str] = Field(default_factory=dict)


class TargetPattern(StrictModel):
    kind: str
    value: str


class CompiledPredicateVersion(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("PV"))
    contract_id: str | None = None
    version: str = "PV-001"
    host_action_patterns: list[HostActionPattern] = Field(default_factory=list)
    target_patterns: list[TargetPattern] = Field(default_factory=list)
    canonical_tags: list[str] = Field(default_factory=list)
    scope_predicate: dict[str, Any] = Field(default_factory=dict)
    lifecycle_predicate: dict[str, Any] = Field(default_factory=dict)
    refines: str | None = None
    status: PredicateStatus = PredicateStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def created_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    def has_binding_predicates(self) -> bool:
        return bool(self.host_action_patterns or self.target_patterns or self.canonical_tags)


class OverridePolicy(StrictModel):
    allowed: bool = True
    requires: OverrideRequirement = OverrideRequirement.EXPLICIT_USER_CONFIRMATION


class Contract(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("MAC"))
    text: str
    kind: ContractKind
    modality: Modality
    strength: Strength = Strength.SOFT
    source: ContractSource
    scope: Scope
    lifecycle: Lifecycle = Field(default_factory=Lifecycle)
    action_constraints: ActionConstraints = Field(default_factory=ActionConstraints)
    compiled_predicates: CompiledPredicateVersion | None = None
    override: OverridePolicy = Field(default_factory=OverridePolicy)
    status: ContractStatus = ContractStatus.ACTIVE
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    supersedes: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_contract_semantics(self) -> Self:
        if self.kind == ContractKind.PROHIBITION and self.modality != Modality.MUST_NOT:
            raise ValueError("prohibition contracts must use MUST_NOT modality")
        if self.kind == ContractKind.FACT:
            if self.modality in {Modality.MUST, Modality.MUST_NOT}:
                raise ValueError("fact contracts cannot use MUST or MUST_NOT modality")
            if self.action_constraints.host_actions or self.action_constraints.canonical_tags:
                raise ValueError("fact contracts cannot bind action constraints")
            if self.compiled_predicates and self.compiled_predicates.has_binding_predicates():
                raise ValueError("fact contracts cannot bind compiled predicates")
        return self

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.lifecycle.is_expired(now)


class ContractEdge(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("E"))
    from_contract: str
    to_contract: str
    relation: EdgeRelation
    scope: Scope
    lifecycle: Lifecycle = Field(default_factory=Lifecycle)
    source: ContractSource | None = None
    status: ContractStatus = ContractStatus.ACTIVE
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def created_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def edge_must_connect_distinct_contracts(self) -> Self:
        if self.from_contract == self.to_contract:
            raise ValueError("contract edge must connect distinct contracts")
        return self


class AvailableAction(StrictModel):
    name: str
    argument_schema: dict[str, Any] = Field(default_factory=dict)
    canonical_tags: list[str] = Field(default_factory=list)
    side_effect: SideEffect = SideEffect.NONE
    description: str | None = None


class SessionContext(StrictModel):
    session_id: str
    conversation_id: str | None = None
    turn_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None


class TimeContext(StrictModel):
    now: datetime = Field(default_factory=utc_now)
    timezone: str = "UTC"

    @field_validator("now")
    @classmethod
    def now_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return value


class WorkspaceContext(StrictModel):
    cwd: str
    repo: str | None = None
    branch: str | None = None


class ToolCall(StrictModel):
    name: str
    raw_arguments: dict[str, Any] = Field(default_factory=dict)


class ActionSignature(StrictModel):
    signature_id: str = Field(default_factory=lambda: prefixed_id("AS"))
    host: str
    agent_family: str
    session: SessionContext
    time: TimeContext = Field(default_factory=TimeContext)
    workspace: WorkspaceContext
    available_actions: list[AvailableAction] = Field(default_factory=list)
    tool: ToolCall
    host_action: str
    canonical_tags: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)
    intent: str = ""
    risk: RiskLevel = RiskLevel.MEDIUM
    side_effect: SideEffect = SideEffect.NONE

    @model_validator(mode="after")
    def host_action_must_be_advertised_when_registry_is_present(self) -> Self:
        if self.available_actions:
            advertised = {action.name for action in self.available_actions}
            if self.host_action not in advertised:
                raise ValueError("host_action must be present in available_actions")
        return self


class IgnoredContract(StrictModel):
    id: str
    reason: str


class GateDecision(StrictModel):
    decision: GateDecisionType
    reason: str
    contracts_used: list[str] = Field(default_factory=list)
    edges_applied: list[str] = Field(default_factory=list)
    match_outcome: MatchOutcome | None = None


class Receipt(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("R"))
    action_id: str = Field(default_factory=lambda: prefixed_id("A"))
    signature_id: str
    session_id: str
    decision: GateDecisionType
    host_action: str
    tool_name: str | None = None
    raw_arguments: dict[str, Any] = Field(default_factory=dict)
    canonical_tags: list[str] = Field(default_factory=list)
    match_outcome: MatchOutcome
    targets: list[str] = Field(default_factory=list)
    intent: str = ""
    contracts_used: list[str] = Field(default_factory=list)
    edges_applied: list[str] = Field(default_factory=list)
    contracts_ignored: list[IgnoredContract] = Field(default_factory=list)
    result: str
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def created_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class AmbiguityEvent(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("AMB"))
    contract_id: str
    predicate_version_id: str
    signature_id: str
    match_outcome: MatchOutcome = MatchOutcome.AMBIGUOUS
    evaluated_at: datetime = Field(default_factory=utc_now)
    reason: str | None = None

    @field_validator("evaluated_at")
    @classmethod
    def evaluated_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def ambiguity_event_must_be_ambiguous(self) -> Self:
        if self.match_outcome != MatchOutcome.AMBIGUOUS:
            raise ValueError("ambiguity events must use ambiguous match_outcome")
        return self


class PredicateEvaluation(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("PE"))
    contract_id: str
    predicate_version_id: str
    signature_id: str
    match_outcome: MatchOutcome
    evaluated_at: datetime = Field(default_factory=utc_now)
    reason: str | None = None

    @field_validator("evaluated_at")
    @classmethod
    def evaluated_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        return value


class SourceSnapshot(StrictModel):
    source_key: str
    adapter: str
    path: str
    workspace: str
    source_kind: SourceKind
    fingerprint: str
    content: str
    observed_at: datetime = Field(default_factory=utc_now)

    @field_validator("observed_at")
    @classmethod
    def observed_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value


class RefinementJob(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("RJ"))
    contract_id: str
    predicate_version_id: str
    status: JobStatus = JobStatus.PENDING
    recent_signature_ids: list[str] = Field(default_factory=list)
    result_predicate_version_id: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("refinement job timestamps must be timezone-aware")
        return value
