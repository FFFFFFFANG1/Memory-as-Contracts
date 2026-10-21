from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from memory_as_contracts.matching import lifecycle_is_active, path_scope_matches
from memory_as_contracts.models import (
    ActionSignature,
    Contract,
    ContractKind,
    ContractStatus,
    RuleEffect,
    Scope,
    ScopeLevel,
)
from memory_as_contracts.policy_ir import policy_target_matches
from memory_as_contracts.store import ContractStore


HookPhase = Literal["pre", "post"]
HookKind = Literal["policy_check", "policy_missing", "action_log"]


@dataclass(frozen=True)
class ActiveHookEntry:
    phase: HookPhase
    kind: HookKind
    contract_id: str | None = None
    scope_level: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class ActiveHookPlan:
    active_paths: tuple[str, ...]
    current_active_prehook: tuple[ActiveHookEntry, ...]
    current_active_posthook: tuple[ActiveHookEntry, ...]
    prehook_contracts: tuple[Contract, ...]


def build_active_hook_plan(
    store: ContractStore,
    signature: ActionSignature,
    *,
    active_paths: Iterable[str],
) -> ActiveHookPlan:
    paths = tuple(_dedupe_paths(active_paths))
    prehooks: list[ActiveHookEntry] = []
    contracts: list[Contract] = []
    for contract in store.list_contracts(
        [ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT],
        include_expired_status=True,
    ):
        if not _can_have_prehook(contract):
            continue
        if not lifecycle_is_active(contract.lifecycle, signature):
            continue
        if not scope_is_active_for_hook(contract.scope, signature, paths):
            continue
        if contract.policy_ir is not None and not policy_target_matches(contract, signature):
            continue
        contracts.append(contract)
        kind: HookKind = "policy_check" if contract.policy_ir is not None else "policy_missing"
        prehooks.append(
            ActiveHookEntry(
                phase="pre",
                kind=kind,
                contract_id=contract.id,
                scope_level=contract.scope.level.value,
                reason=_scope_reason(contract.scope),
            )
        )
    return ActiveHookPlan(
        active_paths=paths,
        current_active_prehook=tuple(prehooks),
        current_active_posthook=(
            ActiveHookEntry(phase="post", kind="action_log", reason="committed_action_log"),
        ),
        prehook_contracts=tuple(contracts),
    )


def signature_with_active_paths(
    signature: ActionSignature,
    active_paths: Iterable[str],
) -> ActionSignature:
    targets = _dedupe_paths([*signature.targets, *active_paths])
    return signature.model_copy(update={"targets": targets})


def candidate_paths_from_signature(signature: ActionSignature) -> list[str]:
    values: list[str] = [*signature.targets]
    for value in _walk_values(signature.tool.raw_arguments):
        if isinstance(value, str):
            values.extend(_paths_from_text(value))
    return _dedupe_paths(
        _normalize_path_candidate(
            value,
            workspace=signature.workspace.root,
            cwd=signature.workspace.cwd,
        )
        for value in values
    )


def scope_is_active_for_hook(
    scope: Scope,
    signature: ActionSignature,
    active_paths: Iterable[str],
) -> bool:
    workspace_root = signature.workspace.root or signature.workspace.cwd
    if scope.user_id and signature.session.user_id and scope.user_id != signature.session.user_id:
        return False
    if scope.workspace and workspace_root and _norm_root(scope.workspace) != _norm_root(workspace_root):
        return False

    if scope.level == ScopeLevel.GLOBAL:
        return True
    if scope.level == ScopeLevel.SESSION:
        return True
    if scope.level == ScopeLevel.WORKSPACE:
        return bool(scope.workspace and workspace_root)
    if scope.level == ScopeLevel.PROJECT:
        return _project_scope_active(scope, signature)
    if scope.level == ScopeLevel.MODULE:
        return _project_scope_active(scope, signature)
    if scope.level == ScopeLevel.PATH:
        return bool(
            scope.path
            and any(_active_path_matches_scope(path, scope.path) for path in active_paths)
        )
    return False


def _can_have_prehook(contract: Contract) -> bool:
    return (
        contract.kind not in {ContractKind.FACT, ContractKind.PREFERENCE}
        and contract.effect != RuleEffect.PREFER
    )


def _project_scope_active(scope: Scope, signature: ActionSignature) -> bool:
    workspace_root = signature.workspace.root or signature.workspace.cwd
    project = scope.project or scope.workspace
    if project is None:
        return False
    if scope.workspace and workspace_root and _norm_root(scope.workspace) != _norm_root(workspace_root):
        return False
    return project in {workspace_root, signature.workspace.repo, scope.workspace}


def _active_path_matches_scope(active_path: str, path_scope: str) -> bool:
    return path_scope_matches(active_path, path_scope)


def _scope_reason(scope: Scope) -> str:
    if scope.level == ScopeLevel.PATH:
        return f"path:{scope.path or ''}"
    return scope.level.value


def _walk_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)
    else:
        yield value


def _paths_from_text(text: str) -> list[str]:
    if "://" in text:
        text = re.sub(r"https?://\S+", " ", text)
    candidates = re.findall(
        r"(?:\.\.?/|/)?(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+/?|"
        r"[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,8}",
        text,
    )
    return [candidate.strip("'\"`:,;()[]{}") for candidate in candidates]


def _normalize_path_candidate(
    value: str | None,
    *,
    workspace: str | None,
    cwd: str | None,
) -> str | None:
    if not value:
        return None
    raw = value.strip().strip("'\"`").replace("\\", "/")
    if not raw or raw.startswith("-") or raw in {".", ".."}:
        return None
    if raw.startswith(("http://", "https://")):
        return None
    workspace_path = Path(workspace).expanduser().resolve(strict=False) if workspace else None
    cwd_path = Path(cwd).expanduser().resolve(strict=False) if cwd else workspace_path
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=False)
    elif cwd_path is not None:
        resolved = (cwd_path / candidate).resolve(strict=False)
    else:
        return raw.removeprefix("./").rstrip("/")
    if workspace_path is not None:
        try:
            return resolved.relative_to(workspace_path).as_posix().rstrip("/")
        except ValueError:
            pass
    return raw.removeprefix("./").rstrip("/")


def _dedupe_paths(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        normalized = value.replace("\\", "/").removeprefix("./").rstrip("/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _norm_root(value: str) -> str:
    return str(Path(value).expanduser().resolve(strict=False))
