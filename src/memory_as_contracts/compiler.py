from __future__ import annotations

import re
import shlex
from fnmatch import fnmatch

from memory_as_contracts.grounding_cache import GroundingCache
from memory_as_contracts.models import (
    ActionSignature,
    AvailableAction,
    CompiledPredicateVersion,
    Contract,
    HostActionPattern,
    MatchOutcome,
    TargetPattern,
)


class PolicyCompiler:
    """Compile contracts into deterministic action-time predicates."""

    path_pattern = re.compile(
        r"(?:under|inside|path|folder)\s+`?([A-Za-z0-9_./*?-]+)`?|in\s+`([A-Za-z0-9_./*?-]+)`",
        re.I,
    )
    glob_pattern = re.compile(r"`?([A-Za-z0-9_.-]+/(?:[A-Za-z0-9_.-]+/)*\*\*?)`?")
    relative_path_pattern = re.compile(
        r"\b(?:[A-Za-z0-9_.-]+/)+(?:[A-Za-z0-9_.-]+)\."
        r"(?:py|js|jsx|ts|tsx|md|json|toml|yaml|yml|txt|lock|rs|go|java|c|cc|cpp|h|css|html|sh)\b"
    )
    bare_file_pattern = re.compile(
        r"\b[A-Za-z0-9_.-]+\.(?:py|js|jsx|ts|tsx|md|json|toml|yaml|yml|txt|lock|rs|go|java|c|cc|cpp|h|css|html|sh)\b"
    )

    def __init__(self, grounding_cache: GroundingCache | None = None) -> None:
        self.grounding_cache = grounding_cache

    def compile(
        self,
        contract: Contract,
        available_actions: list[AvailableAction],
        *,
        version: str = "PV-001",
        refines: str | None = None,
    ) -> CompiledPredicateVersion:
        action_names = {action.name for action in available_actions}
        host_patterns: list[HostActionPattern] = []
        target_patterns: list[TargetPattern] = []
        tags = set(contract.action_constraints.canonical_tags)
        grounding = self._grounding_cache(contract)

        hint = contract.compiled_predicates
        if hint is not None:
            host_patterns.extend(
                grounding.ground_host_patterns(
                    text=contract.text,
                    hint_patterns=hint.host_action_patterns,
                    action_names=action_names,
                )
            )
            target_patterns.extend(
                grounding.ground_targets(
                    text=contract.text,
                    hint_targets=hint.target_patterns,
                    scope_globs=[],
                )
            )
            tags.update(hint.canonical_tags)

        constraint_actions = _narrow_host_actions(contract.action_constraints.host_actions)
        for host_action in constraint_actions:
            if not action_names or host_action in action_names:
                host_patterns.append(HostActionPattern(action=host_action))

        lower = contract.text.lower()
        if "publish" in lower and not any(pattern.action == "git.push" for pattern in host_patterns):
            if "git.push" in action_names:
                host_patterns.append(HostActionPattern(action="git.push"))
            tags.update({"external_write", "publish_code"})
        if any(pattern.action == "git.push" for pattern in host_patterns):
            tags.update({"external_write", "publish_code"})
        if any(pattern.action == "git.commit" for pattern in host_patterns):
            tags.update({"source_modification", "version_control"})
        if any(token in lower for token in ("web search", "web-search", "browse", "browser")):
            if "web.search" in action_names:
                host_patterns.append(HostActionPattern(action="web.search"))
            tags.add("network_read")
        if any(token in lower for token in ("email", "message", "messages", "slack", "send", "notify")):
            for action in ("email.send", "message.send"):
                if not action_names or action in action_names:
                    host_patterns.append(HostActionPattern(action=action))
            tags.update({"external_write", "notify_human"})
        if "npm" in lower and ("not npm" in lower or "do not use npm" in lower):
            host_patterns.append(_command_pattern(action_names, "exec", "npm", None))
            tags.add("dependency_change")
        if any(token in lower for token in ("install", "dependency")):
            if "dependency.install" in action_names:
                host_patterns.append(HostActionPattern(action="dependency.install"))
            else:
                host_patterns.append(HostActionPattern(action="exec"))
            tags.add("dependency_change")
        host_patterns.extend(
            grounding.ground_host_patterns(
                text=contract.text,
                hint_patterns=[],
                action_names=action_names,
            )
        )

        path_match = self.path_pattern.search(contract.text)
        glob_match = self.glob_pattern.search(contract.text)
        relative_path = self.relative_path_pattern.search(contract.text)
        bare_file = _selected_bare_file_target(contract.text, self.bare_file_pattern)
        if relative_path:
            target_patterns.extend(
                grounding.ground_targets(
                    text=contract.text,
                    hint_targets=[
                        TargetPattern(kind="path_glob", value=relative_path.group(0).rstrip(".,;:"))
                    ],
                    scope_globs=[],
                )
            )
        elif path_match or glob_match:
            target_patterns.append(
                TargetPattern(
                    kind="path_glob",
                    value=(
                        (path_match.group(1) or path_match.group(2))
                        if path_match
                        else glob_match.group(1)
                    ).rstrip(".,;:"),
                )
            )
        elif bare_file and any(token in lower for token in ("edit", "write", "delete", "touch", "read")):
            target_patterns.extend(
                grounding.ground_targets(
                    text=contract.text,
                    hint_targets=[TargetPattern(kind="path_glob", value=bare_file)],
                    scope_globs=[],
                )
            )
        elif "generated" in lower and any(token in lower for token in ("edit", "write", "touch")):
            target_patterns.append(TargetPattern(kind="path_glob", value="generated/**"))
        target_patterns.extend(
            grounding.ground_targets(
                text=contract.text,
                hint_targets=[],
                scope_globs=contract.scope.path_globs,
            )
        )

        return CompiledPredicateVersion(
            contract_id=contract.id,
            version=version,
            host_action_patterns=_dedupe_host_patterns(host_patterns),
            target_patterns=_dedupe_target_patterns(target_patterns),
            canonical_tags=sorted(tags),
            scope_predicate=contract.scope.model_dump(mode="json"),
            lifecycle_predicate=contract.lifecycle.model_dump(mode="json"),
            refines=refines,
        )

    def _grounding_cache(self, contract: Contract) -> GroundingCache:
        if self.grounding_cache is not None:
            return self.grounding_cache
        return GroundingCache.from_workspace(contract.scope.workspace)

    def evaluate(
        self,
        predicate: CompiledPredicateVersion,
        signature: ActionSignature,
    ) -> MatchOutcome:
        if not predicate.has_binding_predicates():
            return MatchOutcome.AMBIGUOUS

        if predicate.host_action_patterns:
            action_matches = [
                _host_pattern_matches(pattern, signature)
                for pattern in predicate.host_action_patterns
            ]
            if MatchOutcome.MATCHED not in action_matches:
                if MatchOutcome.AMBIGUOUS in action_matches:
                    return MatchOutcome.AMBIGUOUS
                return MatchOutcome.NOT_MATCHED

        if predicate.target_patterns:
            if not signature.targets:
                return MatchOutcome.AMBIGUOUS
            if not any(
                _target_pattern_matches(pattern, target)
                for pattern in predicate.target_patterns
                for target in signature.targets
            ):
                return MatchOutcome.NOT_MATCHED

        if predicate.canonical_tags and not set(predicate.canonical_tags).intersection(signature.canonical_tags):
            if not predicate.host_action_patterns and not predicate.target_patterns:
                return MatchOutcome.NOT_MATCHED

        return MatchOutcome.MATCHED


def _command_pattern(
    available_action_names: set[str],
    preferred_action: str,
    program: str,
    subcommand: str | None,
) -> HostActionPattern:
    action = preferred_action if preferred_action in available_action_names else "exec"
    return HostActionPattern(action=action, program=program, subcommand=subcommand)


def _selected_bare_file_target(text: str, pattern: re.Pattern[str]) -> str | None:
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    trigger = re.search(r"\b(?:do not|don't|never|must not)\b", text, flags=re.I)
    if trigger is None:
        return matches[0].group(0).rstrip(".,;:")
    after_trigger = [match for match in matches if match.start() >= trigger.start()]
    return (after_trigger[0] if after_trigger else matches[0]).group(0).rstrip(".,;:")


def _narrow_host_actions(host_actions: list[str]) -> list[str]:
    actions = set(host_actions)
    if "exec" in actions and actions - {"exec"}:
        actions.remove("exec")
    return sorted(actions)


def _host_pattern_matches(
    pattern: HostActionPattern,
    signature: ActionSignature,
) -> MatchOutcome:
    if pattern.tool_name is not None and pattern.tool_name != signature.tool.name:
        return MatchOutcome.NOT_MATCHED

    parameter_outcome = _parameter_regex_matches(pattern, signature)
    if parameter_outcome != MatchOutcome.MATCHED:
        return parameter_outcome

    parsed = _parse_signature_command(signature)
    action_is_binding = pattern.action != "*"
    action_matches = not action_is_binding or pattern.action == signature.host_action
    if pattern.program and signature.host_action != "exec" and not action_matches:
        return MatchOutcome.NOT_MATCHED
    if (
        action_is_binding
        and not action_matches
        and pattern.action == "exec"
        and signature.host_action != "exec"
    ):
        return MatchOutcome.NOT_MATCHED
    command_matches = True
    if pattern.program:
        if parsed is None:
            command_matches = False if action_matches else None
        else:
            program, subcommand = parsed
            command_matches = program == pattern.program and (
                pattern.subcommand is None or subcommand == pattern.subcommand
            )
    if action_matches and command_matches is not False:
        return MatchOutcome.MATCHED
    if pattern.program and command_matches is True:
        return MatchOutcome.MATCHED
    if command_matches is None:
        return MatchOutcome.AMBIGUOUS
    return MatchOutcome.NOT_MATCHED


def _parameter_regex_matches(
    pattern: HostActionPattern,
    signature: ActionSignature,
) -> MatchOutcome:
    if not pattern.parameter_regex:
        return MatchOutcome.MATCHED
    for key, regex in pattern.parameter_regex.items():
        value = signature.tool.raw_arguments.get(key)
        if value is None:
            return MatchOutcome.NOT_MATCHED
        try:
            if re.search(regex, str(value)) is None:
                return MatchOutcome.NOT_MATCHED
        except re.error:
            return MatchOutcome.AMBIGUOUS
    return MatchOutcome.MATCHED


def _target_pattern_matches(pattern: TargetPattern, target: str) -> bool:
    if pattern.kind == "path_glob":
        if fnmatch(target, pattern.value):
            return True
        if pattern.value.startswith("**/"):
            return fnmatch(target, pattern.value.removeprefix("**/"))
        return False
    return pattern.value == target


def _parse_signature_command(signature: ActionSignature) -> tuple[str, str | None] | None:
    raw = signature.tool.raw_arguments
    command = raw.get("cmd") or raw.get("command")
    if not isinstance(command, str):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    if not tokens:
        return None
    program = tokens[0]
    subcommand = tokens[1] if len(tokens) > 1 else None
    return program, subcommand


def _dedupe_host_patterns(patterns: list[HostActionPattern]) -> list[HostActionPattern]:
    seen: set[tuple[str, str | None, str | None, str | None, tuple[tuple[str, str], ...]]] = set()
    result: list[HostActionPattern] = []
    for pattern in patterns:
        key = (
            pattern.action,
            pattern.tool_name,
            pattern.program,
            pattern.subcommand,
            tuple(sorted(pattern.parameter_regex.items())),
        )
        if key not in seen:
            seen.add(key)
            result.append(pattern)
    return result


def _dedupe_target_patterns(patterns: list[TargetPattern]) -> list[TargetPattern]:
    seen: set[tuple[str, str]] = set()
    result: list[TargetPattern] = []
    for pattern in patterns:
        key = (pattern.kind, pattern.value)
        if key not in seen:
            seen.add(key)
            result.append(pattern)
    return result
