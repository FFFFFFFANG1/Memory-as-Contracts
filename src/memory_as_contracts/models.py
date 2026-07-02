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
    SESSION = "session"
    WORKSPACE = "workspace"
    PATH = "path"
    MODULE = "module"
    PROJECT = "project"
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


class GateDecisionType(StrEnum):
    ALLOW = "allow"
    REJECT = "reject"
    ASK = "ask"


class MatchOutcome(StrEnum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"


class ActionOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class AskRequestStatus(StrEnum):
    REQUIRED = "required"
    RESPONDED = "responded"
    CONSUMED = "consumed"
    CANCELLED = "cancelled"


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


class ValidatorEnforcementShape(StrEnum):
    CHECK_ONLY = "check_only"
    CHECK_UPDATE = "check_update"


class RuleSemantics(StrictModel):
    actions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ContractSource(StrictModel):
    kind: SourceKind
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
    project: str | None = None
    module: str | None = None
    path: str | None = None
    user_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_compact_scope(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "level" not in normalized:
            if normalized.get("path"):
                normalized["level"] = ScopeLevel.PATH.value
            elif normalized.get("module"):
                normalized["level"] = ScopeLevel.MODULE.value
            elif normalized.get("workspace") and not normalized.get("project"):
                normalized["level"] = ScopeLevel.WORKSPACE.value
            elif normalized.get("workspace") or normalized.get("project"):
                normalized["level"] = ScopeLevel.PROJECT.value
            else:
                normalized["level"] = ScopeLevel.GLOBAL.value
        return normalized

    @model_validator(mode="after")
    def validate_scope_boundary(self) -> Self:
        if self.level == ScopeLevel.WORKSPACE and not self.workspace:
            raise ValueError("workspace scope requires workspace")
        if self.level == ScopeLevel.PATH and not self.path:
            raise ValueError("path scope requires path")
        if self.level == ScopeLevel.PROJECT and not (self.workspace or self.project):
            raise ValueError("project scope requires project or workspace")
        if self.level == ScopeLevel.MODULE:
            if not self.module:
                raise ValueError("module scope requires module")
            if not (self.workspace or self.project):
                raise ValueError("module scope requires project or workspace")
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


class ActionLogEntryV1(StrictModel):
    seq: int | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    session_id: str
    agent_id: str
    adapter_id: str
    tool_call_id: str
    tool_name: str
    host_action: str
    arguments: Any = Field(default_factory=dict)
    result: Any | None = None
    result_text: str = ""
    outcome: ActionOutcome = ActionOutcome.UNKNOWN
    reasoning_text: str | None = None
    conversation_id: str | None = None
    turn_id: str | None = None
    user_id: str | None = None
    workspace: str | None = None
    repo: str | None = None
    branch: str | None = None
    targets: list[str] = Field(default_factory=list)
    risk: RiskLevel = RiskLevel.MEDIUM
    side_effect: SideEffect = SideEffect.NONE

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("action log timestamp must be timezone-aware")
        return value


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
    check_patterns: list[ToolPattern] = Field(default_factory=list)
    canonical_tags: list[str] = Field(default_factory=list)
    scope_predicate: dict[str, Any] = Field(default_factory=dict)
    lifecycle_predicate: dict[str, Any] = Field(default_factory=dict)
    refines: str | None = None
    status: PredicateStatus = PredicateStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_patterns(cls, data: Any) -> Any:
        return data

    @field_validator("created_at")
    @classmethod
    def created_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    def has_binding_predicates(self) -> bool:
        return bool(self.check_patterns)

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
    override: OverridePolicy = Field(default_factory=OverridePolicy)
    validity: RuleValidity = Field(default_factory=RuleValidity)
    validator_enforcement_shape: ValidatorEnforcementShape = ValidatorEnforcementShape.CHECK_ONLY
    check_patterns: list[ToolPattern] = Field(default_factory=list)
    update_patterns: list[ToolPattern] = Field(default_factory=list)
    state_fields: list[str] = Field(default_factory=list)

    kind: ContractKind = ContractKind.PREFERENCE
    modality: Modality = Modality.SHOULD
    strength: Strength = Strength.SOFT
    source: ContractSource
    lifecycle: Lifecycle = Field(default_factory=Lifecycle)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    supersedes: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def populate_internal_rule_metadata(cls, data: Any) -> Any:
        """Derive internal audit metadata from canonical Rule fields.

        This intentionally does not translate legacy operational fields. Old
        payloads must pass through schema_compat.normalize_rule_payload first.
        """

        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        missing = object()
        valid_until = normalized.pop("valid_until", missing)
        if valid_until is missing:
            valid_until = normalized.pop("validate_until", missing)
        if "validity" not in normalized and valid_until is not missing:
            normalized["validity"] = {"until": valid_until}
        effect = _raw_enum_value(normalized.get("effect"))
        kind = _raw_enum_value(normalized.get("kind"))
        modality = _raw_enum_value(normalized.get("modality"))
        if effect is None:
            normalized["effect"] = _effect_for_internal_shape(kind, modality)
            effect = normalized["effect"]
        if kind is None or modality is None:
            derived_kind, derived_modality, derived_strength = _internal_shape_for_effect(effect)
            normalized.setdefault("kind", derived_kind)
            normalized.setdefault("modality", derived_modality)
            normalized.setdefault("strength", derived_strength)

        source = normalized.get("source")
        source_payload = (
            source.model_dump(mode="json") if hasattr(source, "model_dump") else source
        )
        authority = _raw_enum_value(normalized.get("authority"))
        if authority is None and isinstance(source_payload, dict):
            normalized["authority"] = _authority_for_source_kind(
                _raw_enum_value(source_payload.get("kind"))
            )
            authority = normalized["authority"]
        if source is None:
            normalized["source"] = {
                "kind": _source_kind_for_authority(authority),
            }

        lifecycle = normalized.get("lifecycle")
        lifecycle_payload = (
            lifecycle.model_dump(mode="json") if hasattr(lifecycle, "model_dump") else lifecycle
        )
        validity = normalized.get("validity")
        validity_payload = (
            validity.model_dump(mode="json") if hasattr(validity, "model_dump") else validity
        )
        if validity is None and isinstance(lifecycle_payload, dict):
            normalized["validity"] = {
                "from": lifecycle_payload.get("effective_from"),
                "until": lifecycle_payload.get("expires_at"),
            }
        if lifecycle is None and isinstance(validity_payload, dict):
            until = validity_payload.get("until")
            normalized["lifecycle"] = {
                "type": "bounded_time" if until else "until_revoked",
                "effective_from": validity_payload.get("from")
                or validity_payload.get("start"),
                "expires_at": until,
                "until_revoked": until is None,
            }
        return normalized

    @model_validator(mode="after")
    def validate_contract_semantics(self) -> Self:
        if self.kind == ContractKind.PROHIBITION and self.modality != Modality.MUST_NOT:
            raise ValueError("prohibition contracts must use MUST_NOT modality")
        if self.kind == ContractKind.FACT:
            if self.modality in {Modality.MUST, Modality.MUST_NOT}:
                raise ValueError("fact contracts cannot use MUST or MUST_NOT modality")
            if self.semantics.actions or self.semantics.tags:
                raise ValueError("fact contracts cannot bind rule semantics")
            if self.check_patterns or self.update_patterns:
                raise ValueError("fact contracts cannot bind operational patterns")
        return self

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.validity.is_expired(now) or self.lifecycle.is_expired(now)


Rule = Contract


def _raw_enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value.value) if hasattr(value, "value") else str(value)


def _effect_for_internal_shape(kind: str | None, modality: str | None) -> str:
    if kind == ContractKind.PROHIBITION.value or modality == Modality.MUST_NOT.value:
        return RuleEffect.DENY.value
    if kind == ContractKind.EXCEPTION.value or modality == Modality.MAY.value:
        return RuleEffect.ALLOW.value
    if kind in {ContractKind.REQUIREMENT.value, ContractKind.PROCEDURE.value}:
        return RuleEffect.REQUIRE.value
    if modality == Modality.MUST.value:
        return RuleEffect.REQUIRE.value
    return RuleEffect.PREFER.value


def _internal_shape_for_effect(effect: str | None) -> tuple[str, str, str]:
    if effect == RuleEffect.DENY.value:
        return (
            ContractKind.PROHIBITION.value,
            Modality.MUST_NOT.value,
            Strength.HARD.value,
        )
    if effect == RuleEffect.REQUIRE.value:
        return ContractKind.REQUIREMENT.value, Modality.MUST.value, Strength.HARD.value
    if effect == RuleEffect.ALLOW.value:
        return ContractKind.EXCEPTION.value, Modality.MAY.value, Strength.SOFT.value
    return ContractKind.PREFERENCE.value, Modality.SHOULD.value, Strength.SOFT.value


def _authority_for_source_kind(source_kind: str | None) -> str:
    mapping = {
        SourceKind.USER_TURN.value: RuleAuthority.USER_EXPLICIT.value,
        SourceKind.PROJECT_DOC.value: RuleAuthority.PROJECT_INSTRUCTION.value,
        SourceKind.MEMORY_FILE.value: RuleAuthority.MEMORY_IMPORT.value,
        SourceKind.USER_PROFILE.value: RuleAuthority.USER_PROFILE.value,
        SourceKind.TOOL_OBSERVATION.value: RuleAuthority.TOOL_OBSERVATION.value,
    }
    return mapping.get(source_kind, RuleAuthority.AGENT_INFERRED.value)


def _source_kind_for_authority(authority: str | None) -> str:
    mapping = {
        RuleAuthority.USER_EXPLICIT.value: SourceKind.USER_TURN.value,
        RuleAuthority.PROJECT_INSTRUCTION.value: SourceKind.PROJECT_DOC.value,
        RuleAuthority.MEMORY_IMPORT.value: SourceKind.MEMORY_FILE.value,
        RuleAuthority.USER_PROFILE.value: SourceKind.USER_PROFILE.value,
        RuleAuthority.TOOL_OBSERVATION.value: SourceKind.TOOL_OBSERVATION.value,
    }
    return mapping.get(authority, SourceKind.AGENT_INFERRED.value)


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
    root: str | None = None
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
    validator_verdicts: list[dict[str, Any]] = Field(default_factory=list)
    ask_request_id: str | None = None
    result: str
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def created_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
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


class ValidatorVersion(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("VV"))
    contract_id: str
    enforcement_shape: ValidatorEnforcementShape
    check_code: str
    update_code: str | None = None
    check_patterns: list[ToolPattern] = Field(default_factory=list)
    update_patterns: list[ToolPattern] = Field(default_factory=list)
    state_schema_version: str = "state-v1"
    state_fields: list[str] = Field(default_factory=list)
    shared_states: dict[str, Any] = Field(default_factory=dict)
    sandbox_policy_version: str = "subprocess-v1"
    action_log_search_spec_version: str = "ActionLogSearchSpecV1"
    snippet_hash: str = ""
    verification_hash: str = ""
    verified_at: datetime | None = None
    status: PredicateStatus = PredicateStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def migrate_split_hook_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        if "check_code" not in migrated and migrated.get("snippet") is not None:
            migrated["check_code"] = migrated["snippet"]
        if "shared_states" not in migrated and isinstance(migrated.get("initial_state"), dict):
            migrated["shared_states"] = migrated["initial_state"]
        if not migrated.get("state_fields") and isinstance(migrated.get("shared_states"), dict):
            migrated["state_fields"] = sorted(migrated["shared_states"])
        return migrated

    @field_validator("created_at", "verified_at")
    @classmethod
    def validator_created_at_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("validator version timestamp must be timezone-aware")
        return value


class ValidatorState(StrictModel):
    validator_version_id: str
    scope_key: str
    contract_id: str
    state: dict[str, Any] = Field(default_factory=dict)
    revision: int = Field(default=0, ge=0)
    last_applied_seq: int | None = None
    degraded: bool = False
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("updated_at")
    @classmethod
    def validator_state_updated_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("validator state timestamp must be timezone-aware")
        return value


class ValidatorVerdict(StrictModel):
    decision: GateDecisionType
    reason: str
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AskRequest(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("ASK"))
    session_id: str
    task_id: str | None = None
    adapter_id: str
    tool_name: str
    rule_ids: list[str] = Field(default_factory=list)
    status: AskRequestStatus = AskRequestStatus.REQUIRED
    created_at: datetime = Field(default_factory=utc_now)
    responded_at: datetime | None = None
    responded_turn_id: str | None = None
    expires_at: datetime | None = None
    consumed_at: datetime | None = None

    @field_validator("created_at", "responded_at", "expires_at", "consumed_at")
    @classmethod
    def ask_request_times_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("ask request timestamps must be timezone-aware")
        return value


class ValidatorInstallationStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "fail"


class ValidatorInstallationRecord(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("VI"))
    contract_id: str
    status: ValidatorInstallationStatus
    validator_version_id: str | None = None
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def installation_time_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("validator installation timestamp must be timezone-aware")
        return value


class ValidatorStateTransition(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("VST"))
    validator_version_id: str
    scope_key: str
    action_log_seq: int
    from_revision: int
    to_revision: int
    state_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class ValidatorRuntimeErrorRecord(StrictModel):
    id: str = Field(default_factory=lambda: prefixed_id("VRE"))
    validator_version_id: str
    contract_id: str
    scope_key: str
    phase: str
    action_log_seq: int | None = None
    error_type: str
    message: str
    replay_required: bool = False
    created_at: datetime = Field(default_factory=utc_now)
