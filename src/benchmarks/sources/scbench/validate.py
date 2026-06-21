from __future__ import annotations

from itertools import combinations

from benchmarks.schemas.models import ContractNode
from benchmarks.sources.scbench.models import (
    RelationPattern,
    ScbenchBuildValidationReport,
    ScbenchPreRunBuild,
    ScbenchTaskCandidate,
)

ALLOWING_MODALITIES = {"must", "may", "prefer"}
BLOCKING_MODALITIES = {"must_not", "ask_before"}
CONFLICT_DEFINING_EDGES = {"exception_to", "overrides", "supersedes", "refines", "conflicts_with"}


def validate_scbench_build(
    *,
    task: ScbenchTaskCandidate,
    build: ScbenchPreRunBuild,
) -> ScbenchBuildValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    if build.task_id != task.problem_id:
        errors.append(f"build task_id {build.task_id!r} does not match selected task {task.problem_id!r}")
    if build.decomposition.source_task_id != task.problem_id:
        errors.append("decomposition source_task_id does not match selected task")

    boundary_errors = _validate_task_boundary(task, build)
    blueprint_errors = _validate_blueprint_independence(task, build)
    conflict_errors = _validate_no_undefined_rule_conflicts(build)
    mapping_errors = _validate_rule_task_mapping(task, build)
    errors.extend(boundary_errors)
    errors.extend(blueprint_errors)
    errors.extend(conflict_errors)
    errors.extend(mapping_errors)

    accepted = not errors
    return ScbenchBuildValidationReport(
        task_id=task.problem_id,
        boundary_consistent=not boundary_errors,
        blueprint_independent=not blueprint_errors,
        no_undefined_rule_conflicts=not conflict_errors,
        rules_map_to_task=not mapping_errors,
        accepted=accepted,
        errors=errors,
        warnings=warnings,
    )


def _validate_task_boundary(task: ScbenchTaskCandidate, build: ScbenchPreRunBuild) -> list[str]:
    errors: list[str] = []
    checkpoint_ids = {checkpoint.checkpoint_id for checkpoint in task.checkpoints}
    subtask_ids = {subtask.id for subtask in build.decomposition.subtasks}
    if not build.decomposition.subtasks:
        return ["decomposition has no subtasks"]

    covered_checkpoints_by_subtask: set[str] = set()
    for subtask in build.decomposition.subtasks:
        unknown = set(subtask.source_checkpoint_ids) - checkpoint_ids
        if unknown:
            errors.append(f"subtask {subtask.id} references unknown checkpoints {sorted(unknown)}")
        covered_checkpoints_by_subtask.update(subtask.source_checkpoint_ids)
        unknown_tests = [
            test_path
            for test_path in subtask.acceptance_tests
            if test_path.startswith("tests/") and not (task.root / test_path).exists()
        ]
        if unknown_tests:
            errors.append(f"subtask {subtask.id} references missing tests {unknown_tests}")

    missing_subtask_checkpoint = checkpoint_ids - covered_checkpoints_by_subtask
    if missing_subtask_checkpoint:
        errors.append(f"checkpoints missing from subtasks: {sorted(missing_subtask_checkpoint)}")

    covered_checkpoints_by_requirements: set[str] = set()
    for coverage in build.decomposition.requirement_coverage:
        if coverage.checkpoint_id not in checkpoint_ids:
            errors.append(f"coverage references unknown checkpoint {coverage.checkpoint_id}")
            continue
        unknown_subtasks = set(coverage.covered_by_subtask_ids) - subtask_ids
        if unknown_subtasks:
            errors.append(
                f"coverage for {coverage.checkpoint_id} references unknown subtasks "
                f"{sorted(unknown_subtasks)}"
            )
        if not coverage.requirement_ref.strip():
            errors.append(f"coverage for {coverage.checkpoint_id} has empty requirement_ref")
            continue
        if not _requirement_ref_in_checkpoint(task, coverage.checkpoint_id, coverage.requirement_ref):
            errors.append(
                f"coverage requirement_ref is not an exact substring of {coverage.checkpoint_id}: "
                f"{coverage.requirement_ref!r}"
            )
        covered_checkpoints_by_requirements.add(coverage.checkpoint_id)

    missing_requirement_checkpoint = checkpoint_ids - covered_checkpoints_by_requirements
    if missing_requirement_checkpoint:
        errors.append(
            f"checkpoints missing requirement coverage: {sorted(missing_requirement_checkpoint)}"
        )
    return errors


def _validate_blueprint_independence(
    task: ScbenchTaskCandidate,
    build: ScbenchPreRunBuild,
) -> list[str]:
    errors: list[str] = []
    blueprint = build.rule_blueprint
    if blueprint.source_task_id != task.problem_id:
        errors.append("blueprint source_task_id does not match selected task")
    if len(blueprint.blueprints) < 3 or len(blueprint.blueprints) > 6:
        errors.append("blueprint must contain 3-6 rule blueprints")
    if len(build.contract_graph.edges) < 1 or len(build.contract_graph.edges) > 3:
        errors.append("instantiated graph must contain 1-3 relation edges")

    declared_scope_levels = set(blueprint.target_scope_levels)
    actual_scope_levels = {rule.scope_level for rule in blueprint.blueprints}
    if len(declared_scope_levels | actual_scope_levels) < 2:
        errors.append("blueprint must target at least two scope levels")

    blueprint_ids = {rule.blueprint_id for rule in blueprint.blueprints}
    instantiated_ids = {node.blueprint_id for node in build.contract_graph.nodes if node.blueprint_id}
    for node in build.contract_graph.nodes:
        if not node.blueprint_id:
            errors.append(f"contract {node.id} is missing blueprint_id")
        elif node.blueprint_id not in blueprint_ids:
            errors.append(f"contract {node.id} references unknown blueprint {node.blueprint_id}")

    for rule in blueprint.blueprints:
        if rule.instantiate and rule.relation_pattern != "independent_distractor":
            if rule.blueprint_id not in instantiated_ids:
                errors.append(f"blueprint {rule.blueprint_id} was not instantiated")
        if _is_broad_style_rule(rule.concrete_action_focus) or _is_broad_style_rule(rule.rule_intent):
            errors.append(f"blueprint {rule.blueprint_id} is a broad style rule, not an action predicate")
        if _blueprint_text_copies_task_spec(task, rule.rule_intent):
            errors.append(f"blueprint {rule.blueprint_id} appears copied from task spec")

    for node in build.contract_graph.nodes:
        matching = next(
            (rule for rule in blueprint.blueprints if rule.blueprint_id == node.blueprint_id),
            None,
        )
        if matching is None:
            continue
        if node.modality != matching.modality:
            errors.append(f"contract {node.id} modality does not match blueprint {matching.blueprint_id}")
        if not _texts_overlap(node.surface_text, matching.rule_intent):
            errors.append(f"contract {node.id} surface_text does not trace to blueprint intent")
        if _surface_copies_linked_requirement(node, build):
            errors.append(f"contract {node.id} surface_text appears copied from task requirement")

    errors.extend(_validate_blueprint_relation_targets(build))
    errors.extend(_validate_blueprint_lifecycle_targets(build))
    return errors


def _validate_blueprint_relation_targets(build: ScbenchPreRunBuild) -> list[str]:
    pattern = build.rule_blueprint.target_relation_pattern
    edge_types = {edge.type for edge in build.contract_graph.edges}
    errors = _relation_pattern_errors(pattern, edge_types)
    if pattern == "unresolved_conflict" and "ask" not in build.rule_blueprint.target_decision_mix:
        errors.append("blueprint declares unresolved_conflict but target_decision_mix has no ask")
    return errors


def _relation_pattern_errors(pattern: RelationPattern, edge_types: set[str]) -> list[str]:
    if pattern == "narrow_exception" and "exception_to" not in edge_types:
        return ["blueprint declares narrow_exception but graph has no exception_to edge"]
    if pattern == "override_or_supersession" and not ({"overrides", "supersedes"} & edge_types):
        return ["blueprint declares override_or_supersession but graph has no override/supersedes edge"]
    if pattern == "unresolved_conflict" and "conflicts_with" not in edge_types:
        return ["blueprint declares unresolved_conflict but graph has no conflicts_with edge"]
    if pattern == "temporal_activation_expiry_or_revocation":
        return []
    if pattern == "scope_selection_without_conflict":
        return []
    if pattern == "independent_distractor":
        return []
    return []


def _validate_blueprint_lifecycle_targets(build: ScbenchPreRunBuild) -> list[str]:
    pattern = build.rule_blueprint.target_lifecycle_pattern
    nodes = build.contract_graph.nodes
    has_change = any(
        node.lifecycle.effective_from_event > 0
        or node.lifecycle.effective_until_event is not None
        or node.lifecycle.revoked_at_event is not None
        for node in nodes
    )
    if pattern in {"temporal_activation", "expiry", "revocation"} and not has_change:
        return [f"blueprint declares {pattern} but graph has no lifecycle change"]
    if not has_change:
        return ["graph must include at least one lifecycle change"]
    return []


def _validate_no_undefined_rule_conflicts(build: ScbenchPreRunBuild) -> list[str]:
    errors: list[str] = []
    relation_pairs = {
        frozenset((edge.source, edge.target))
        for edge in build.contract_graph.edges
        if edge.type in CONFLICT_DEFINING_EDGES
    }
    for left, right in combinations(build.contract_graph.nodes, 2):
        if not _potentially_conflicting(left, right):
            continue
        if frozenset((left.id, right.id)) not in relation_pairs:
            errors.append(f"rules {left.id} and {right.id} have undefined conflict")
    return errors


def _validate_rule_task_mapping(task: ScbenchTaskCandidate, build: ScbenchPreRunBuild) -> list[str]:
    errors: list[str] = []
    contract_ids = {node.id for node in build.contract_graph.nodes}
    linked_contract_ids = {link.contract_id for link in build.rule_task_links}
    subtask_ids = {subtask.id for subtask in build.decomposition.subtasks}

    missing_links = contract_ids - linked_contract_ids
    if missing_links:
        errors.append(f"contracts missing rule_task_links: {sorted(missing_links)}")

    for link in build.rule_task_links:
        if link.contract_id not in contract_ids:
            errors.append(f"rule_task_link references unknown contract {link.contract_id}")
        unknown_subtasks = set(link.subtask_ids) - subtask_ids
        if unknown_subtasks:
            errors.append(
                f"rule_task_link for {link.contract_id} references unknown subtasks "
                f"{sorted(unknown_subtasks)}"
            )
        if not link.requirement_refs:
            errors.append(f"rule_task_link for {link.contract_id} has no requirement_refs")
        for requirement_ref in link.requirement_refs:
            if not requirement_ref.strip():
                errors.append(f"rule_task_link for {link.contract_id} has empty requirement_ref")
                continue
            if not _requirement_ref_in_any_checkpoint(task, requirement_ref):
                errors.append(
                    f"rule_task_link for {link.contract_id} has requirement_ref outside task: "
                    f"{requirement_ref!r}"
                )
    return errors


def _requirement_ref_in_checkpoint(
    task: ScbenchTaskCandidate,
    checkpoint_id: str,
    requirement_ref: str,
) -> bool:
    checkpoint = next(
        checkpoint for checkpoint in task.checkpoints if checkpoint.checkpoint_id == checkpoint_id
    )
    return _normalized(requirement_ref) in _normalized(checkpoint.spec_text)


def _requirement_ref_in_any_checkpoint(task: ScbenchTaskCandidate, requirement_ref: str) -> bool:
    needle = _normalized(requirement_ref)
    return any(needle in _normalized(checkpoint.spec_text) for checkpoint in task.checkpoints)


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _is_broad_style_rule(text: str) -> bool:
    lowered = text.lower()
    broad_phrases = (
        "clean code",
        "be careful",
        "best practice",
        "maintainable",
        "well structured",
        "readable code",
        "good style",
    )
    return any(phrase in lowered for phrase in broad_phrases)


def _blueprint_text_copies_task_spec(task: ScbenchTaskCandidate, text: str) -> bool:
    needle = _normalized(text).lower()
    if len(needle) < 40:
        return False
    return any(needle in _normalized(checkpoint.spec_text).lower() for checkpoint in task.checkpoints)


def _texts_overlap(left: str, right: str) -> bool:
    left_tokens = {token for token in _normalized(left).lower().split() if len(token) >= 4}
    right_tokens = {token for token in _normalized(right).lower().split() if len(token) >= 4}
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) >= min(2, len(right_tokens))


def _surface_copies_linked_requirement(node: ContractNode, build: ScbenchPreRunBuild) -> bool:
    surface = _normalized(node.surface_text).lower()
    if len(surface) < 30:
        return False
    for link in build.rule_task_links:
        if link.contract_id != node.id:
            continue
        for requirement_ref in link.requirement_refs:
            requirement = _normalized(requirement_ref).lower()
            if surface == requirement or surface in requirement or requirement in surface:
                return True
    return False


def _potentially_conflicting(left: ContractNode, right: ContractNode) -> bool:
    if not _modalities_conflict(left.modality, right.modality):
        return False
    if not _predicates_overlap(left, right):
        return False
    if not _scopes_overlap(left.scope, right.scope):
        return False
    if not _lifecycles_overlap(left, right):
        return False
    return True


def _modalities_conflict(left: str, right: str) -> bool:
    return (
        left in ALLOWING_MODALITIES
        and right in BLOCKING_MODALITIES
        or right in ALLOWING_MODALITIES
        and left in BLOCKING_MODALITIES
    )


def _predicates_overlap(left: ContractNode, right: ContractNode) -> bool:
    lp = left.action_predicate
    rp = right.action_predicate
    if lp.family != rp.family:
        return False
    for attr in ("object", "target"):
        lv = getattr(lp, attr)
        rv = getattr(rp, attr)
        if lv is not None and rv is not None and lv != rv:
            return False
    return True


def _scopes_overlap(left_scope: dict, right_scope: dict) -> bool:
    for key in set(left_scope) & set(right_scope):
        left = left_scope[key]
        right = right_scope[key]
        if left is not None and right is not None and left != right:
            return False
    return True


def _lifecycles_overlap(left: ContractNode, right: ContractNode) -> bool:
    left_start = left.lifecycle.effective_from_event
    right_start = right.lifecycle.effective_from_event
    left_end = left.lifecycle.revoked_at_event or left.lifecycle.effective_until_event or float("inf")
    right_end = right.lifecycle.revoked_at_event or right.lifecycle.effective_until_event or float("inf")
    return max(left_start, right_start) < min(left_end, right_end)
