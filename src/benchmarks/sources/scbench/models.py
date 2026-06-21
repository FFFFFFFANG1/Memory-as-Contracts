from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from benchmarks.schemas.models import ContractGraph


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScbenchCheckpoint(StrictModel):
    checkpoint_id: str
    order: int
    spec_path: Path
    spec_text: str
    test_files: list[Path] = Field(default_factory=list)


class ScbenchTaskCandidate(StrictModel):
    problem_id: str
    root: Path
    description: str
    difficulty: str | None = None
    category: str | None = None
    entry_file: str | None = None
    tags: list[str] = Field(default_factory=list)
    checkpoints: list[ScbenchCheckpoint]
    selection_score: int

    @field_validator("checkpoints")
    @classmethod
    def require_checkpoints(cls, value: list[ScbenchCheckpoint]) -> list[ScbenchCheckpoint]:
        if not value:
            raise ValueError("SCBench candidate must have checkpoints")
        return value


class ScbenchSubtask(StrictModel):
    id: str
    title: str
    objective: str
    source_checkpoint_ids: list[str]
    requirements: list[str]
    acceptance_tests: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)


class RequirementCoverage(StrictModel):
    checkpoint_id: str
    requirement_ref: str
    covered_by_subtask_ids: list[str]


class TaskDecomposition(StrictModel):
    source_task_id: str
    subtasks: list[ScbenchSubtask]
    requirement_coverage: list[RequirementCoverage]
    notes: str | None = None

    @model_validator(mode="after")
    def validate_subtask_ids(self) -> "TaskDecomposition":
        ids = [subtask.id for subtask in self.subtasks]
        if len(set(ids)) != len(ids):
            raise ValueError("subtask ids must be unique")
        known = set(ids)
        for subtask in self.subtasks:
            unknown = set(subtask.depends_on) - known
            if unknown:
                raise ValueError(f"subtask {subtask.id} depends on unknown subtasks {sorted(unknown)}")
        return self


class RuleTaskLink(StrictModel):
    contract_id: str
    subtask_ids: list[str]
    requirement_refs: list[str]
    rationale: str


ScopeLevel = Literal["global", "per_project", "per_component", "per_path", "per_phase", "per_tool"]
LifecyclePattern = Literal[
    "session",
    "task",
    "checkpoint",
    "temporal_activation",
    "expiry",
    "revocation",
]
RelationPattern = Literal[
    "scope_selection_without_conflict",
    "temporal_activation_expiry_or_revocation",
    "narrow_exception",
    "override_or_supersession",
    "unresolved_conflict",
    "independent_distractor",
]
PlacementStyle = Literal["embedded", "direct"]


class RuleBlueprint(StrictModel):
    blueprint_id: str
    scope_level: ScopeLevel
    modality: str
    rule_intent: str
    lifecycle_pattern: LifecyclePattern
    relation_pattern: RelationPattern
    concrete_action_focus: str
    distractor_intent: str | None = None
    why_this_tests_memory: str
    intended_decision: Literal["allow", "reject", "ask"]
    placement_style: PlacementStyle = "embedded"
    instantiate: bool = True

    @field_validator("concrete_action_focus", "rule_intent", "why_this_tests_memory")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blueprint text fields must not be empty")
        return value


class RuleBlueprintSet(StrictModel):
    source_task_id: str
    target_relation_pattern: RelationPattern
    target_decision_mix: list[Literal["allow", "reject", "ask"]]
    target_scope_levels: list[ScopeLevel]
    target_lifecycle_pattern: LifecyclePattern
    placement_style: PlacementStyle
    quota_rationale: str
    blueprints: list[RuleBlueprint]

    @model_validator(mode="after")
    def validate_blueprints(self) -> "RuleBlueprintSet":
        ids = [blueprint.blueprint_id for blueprint in self.blueprints]
        if len(set(ids)) != len(ids):
            raise ValueError("blueprint ids must be unique")
        if not self.blueprints:
            raise ValueError("rule blueprint set must not be empty")
        return self


class GroundedRuleGraph(StrictModel):
    task_id: str
    contract_graph: ContractGraph
    rule_task_links: list[RuleTaskLink]


class ScbenchPreRunBuild(StrictModel):
    task_id: str
    decomposition: TaskDecomposition
    rule_blueprint: RuleBlueprintSet
    contract_graph: ContractGraph
    rule_task_links: list[RuleTaskLink]


class ScbenchBuildValidationReport(StrictModel):
    task_id: str
    boundary_consistent: bool
    blueprint_independent: bool = True
    no_undefined_rule_conflicts: bool
    rules_map_to_task: bool
    accepted: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ScbenchBuildArtifact(StrictModel):
    source: Literal["scbench"] = "scbench"
    task: ScbenchTaskCandidate
    build: ScbenchPreRunBuild
    validation: ScbenchBuildValidationReport
    builder_model: str
    prompt_hashes: dict[str, str]
