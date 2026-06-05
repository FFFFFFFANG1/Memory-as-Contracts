from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Self
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from memory_as_contracts.schema_compat import (
    normalize_rule_payload as normalize_rule_payload_compat,
    tool_patterns_from_host_patterns,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def prefixed_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


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


class RuleEffect(StrEnum):
    DENY = "deny"
    ALLOW = "allow"
    REQUIRE = "require"
    PREFER = "prefer"


class RuleAuthority(StrEnum):
    USER_EXPLICIT = "user_explicit"
    PROJECT_INSTRUCTION = "project_instruction"
    MEMORY_IMPORT = "memory_import"
    USER_PROFILE = "user_profile"
    TOOL_OBSERVATION = "tool_observation"
    AGENT_INFERRED = "agent_inferred"


class RuleOverrideType(StrEnum):
    NONE = "none"
    EXPLICIT_USER_CURRENT_TURN = "explicit_user_current_turn"
    EXPLICIT_USER_CONFIRMATION = "explicit_user_confirmation"


class RuleSemantics(StrictModel):
    actions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


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

    @model_validator(mode="before")
    @classmethod
    def normalize_compact_scope(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        paths = normalized.pop("paths", None)
        if paths is not None and "path_globs" not in normalized:
            normalized["path_globs"] = paths
        if "level" not in normalized:
            if normalized.get("path_globs"):
                normalized["level"] = ScopeLevel.PATH.value
            elif normalized.get("task"):
                normalized["level"] = ScopeLevel.TASK.value
            elif normalized.get("repo"):
                normalized["level"] = ScopeLevel.REPO.value
            elif normalized.get("workspace"):
                normalized["level"] = ScopeLevel.PROJECT.value
            else:
                normalized["level"] = ScopeLevel.GLOBAL.value
        return normalized

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


class ArgPattern(StrictModel):
    equals: Any | None = None
    regex: str | None = None
    contains: str | None = None
    path_glob: str | None = None
    mentions_path_glob: str | None = None

    def is_empty(self) -> bool:
        return (
            self.equals is None
            and self.regex is None
            and self.contains is None
            and self.path_glob is None
            and self.mentions_path_glob is None
        )


class ToolPattern(StrictModel):
    tool: str
    args: dict[str, ArgPattern] = Field(default_factory=dict)


class RuleValidity(StrictModel):
    start: datetime = Field(default_factory=utc_now, alias="from")
    until: datetime | None = None

    @field_validator("start", "until")
    @classmethod
    def validity_times_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("validity timestamps must be timezone-aware")
        return value

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.until is None:
            return False
        check_time = now or utc_now()
        return self.until <= check_time


class RulePatternVersion(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("PV"))
    contract_id: str | None = None
    version: str = "PV-001"
    host_action_patterns: list[HostActionPattern] = Field(default_factory=list)
    target_patterns: list[TargetPattern] = Field(
        default_factory=list,
        validation_alias=AliasChoices("target_patterns", "targets"),
    )
    tool_patterns: list[ToolPattern] = Field(default_factory=list)
    canonical_tags: list[str] = Field(default_factory=list)
    scope_predicate: dict[str, Any] = Field(default_factory=dict)
    lifecycle_predicate: dict[str, Any] = Field(default_factory=dict)
    refines: str | None = None
    status: PredicateStatus = PredicateStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_pattern_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "targets" in normalized and "target_patterns" not in normalized:
            normalized["target_patterns"] = normalized.pop("targets")
        if not normalized.get("tool_patterns") and normalized.get("host_action_patterns"):
            normalized["tool_patterns"] = tool_patterns_from_host_patterns(
                normalized.get("host_action_patterns", [])
            )
        return normalized

    @field_validator("created_at")
    @classmethod
    def created_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    def has_binding_predicates(self) -> bool:
        return bool(self.tool_patterns or self.target_patterns)

    @property
    def targets(self) -> list[TargetPattern]:
        return self.target_patterns


CompiledPredicateVersion = RulePatternVersion


class OverridePolicy(StrictModel):
    allowed: bool = True
    requires: OverrideRequirement = OverrideRequirement.EXPLICIT_USER_CONFIRMATION
    type: RuleOverrideType = RuleOverrideType.EXPLICIT_USER_CURRENT_TURN


class Contract(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("MAC"))
    text: str
    effect: RuleEffect = RuleEffect.PREFER
    status: ContractStatus = ContractStatus.ACTIVE
    authority: RuleAuthority = RuleAuthority.AGENT_INFERRED
    scope: Scope
    semantics: RuleSemantics = Field(default_factory=RuleSemantics)
    tool_patterns: list[ToolPattern] = Field(default_factory=list)
    targets: list[TargetPattern] = Field(default_factory=list)
    override: OverridePolicy = Field(default_factory=OverridePolicy)
    validity: RuleValidity = Field(default_factory=RuleValidity)

    kind: ContractKind = ContractKind.PREFERENCE
    modality: Modality = Modality.SHOULD
    strength: Strength = Strength.SOFT
    source: ContractSource
    lifecycle: Lifecycle = Field(default_factory=Lifecycle)
    action_constraints: ActionConstraints = Field(default_factory=ActionConstraints)
    compiled_predicates: CompiledPredicateVersion | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    supersedes: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_rule_payload(cls, data: Any) -> Any:
        return normalize_rule_payload_compat(data)

    @model_validator(mode="after")
    def validate_contract_semantics(self) -> Self:
        if self.kind == ContractKind.PROHIBITION and self.modality != Modality.MUST_NOT:
            raise ValueError("prohibition contracts must use MUST_NOT modality")
        if self.kind == ContractKind.FACT:
            if self.modality in {Modality.MUST, Modality.MUST_NOT}:
                raise ValueError("fact contracts cannot use MUST or MUST_NOT modality")
            if (
                self.action_constraints.host_actions
                or self.action_constraints.canonical_tags
                or self.semantics.actions
                or self.semantics.tags
            ):
                raise ValueError("fact contracts cannot bind action constraints")
            if self.compiled_predicates and self.compiled_predicates.has_binding_predicates():
                raise ValueError("fact contracts cannot bind compiled predicates")
            if self.tool_patterns:
                raise ValueError("fact contracts cannot bind tool patterns")
        return self

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.validity.is_expired(now) or self.lifecycle.is_expired(now)


Rule = Contract


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
    available_actions: list[AvailableAction] = Field(default_factory=list)
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
    pattern_version_id: str = Field(
        validation_alias=AliasChoices("pattern_version_id", "predicate_version_id")
    )
    signature_id: str
    match_outcome: MatchOutcome = MatchOutcome.AMBIGUOUS
    evaluated_at: datetime = Field(default_factory=utc_now)
    reason: str | None = None

    @property
    def predicate_version_id(self) -> str:
        return self.pattern_version_id

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
    pattern_version_id: str = Field(
        validation_alias=AliasChoices("pattern_version_id", "predicate_version_id")
    )
    signature_id: str
    match_outcome: MatchOutcome
    evaluated_at: datetime = Field(default_factory=utc_now)
    reason: str | None = None

    @property
    def predicate_version_id(self) -> str:
        return self.pattern_version_id

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
    pattern_version_id: str = Field(
        validation_alias=AliasChoices("pattern_version_id", "predicate_version_id")
    )
    status: JobStatus = JobStatus.PENDING
    recent_signature_ids: list[str] = Field(default_factory=list)
    result_pattern_version_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "result_pattern_version_id", "result_predicate_version_id"
        ),
    )
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def predicate_version_id(self) -> str:
        return self.pattern_version_id

    @property
    def result_predicate_version_id(self) -> str | None:
        return self.result_pattern_version_id

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("refinement job timestamps must be timezone-aware")
        return value
