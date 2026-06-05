from __future__ import annotations

import re
from fnmatch import fnmatch

from memory_as_contracts.grounding_cache import GroundingCache
from memory_as_contracts.models import (
    ActionSignature,
    ArgPattern,
    AvailableAction,
    Contract,
    MatchOutcome,
    RulePatternVersion,
    TargetPattern,
    ToolPattern,
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
    ) -> RulePatternVersion:
        target_patterns: list[TargetPattern] = []
        tool_patterns: list[ToolPattern] = list(contract.tool_patterns)
        tags = set(contract.semantics.tags)
        grounding = self._grounding_cache(contract)
        target_patterns.extend(
            grounding.ground_targets(
                text=contract.text,
                hint_targets=contract.targets,
                scope_globs=[],
            )
        )

        has_operational_seed = bool(tool_patterns)
        lower = contract.text.lower()
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
        if has_operational_seed:
            tool_patterns.extend(
                _materialize_tool_patterns(
                    contract=contract,
                    target_patterns=target_patterns,
                    available_actions=available_actions,
                )
            )

        return RulePatternVersion(
            contract_id=contract.id,
            version=version,
            tool_patterns=_dedupe_tool_patterns(tool_patterns),
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
        predicate: RulePatternVersion,
        signature: ActionSignature,
    ) -> MatchOutcome:
        if not predicate.has_binding_predicates():
            return MatchOutcome.AMBIGUOUS

        if predicate.tool_patterns:
            tool_matches = [
                _tool_pattern_matches(pattern, signature)
                for pattern in predicate.tool_patterns
            ]
            if MatchOutcome.MATCHED not in tool_matches:
                if tool_matches and all(outcome == MatchOutcome.AMBIGUOUS for outcome in tool_matches):
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

        return MatchOutcome.MATCHED


def _selected_bare_file_target(text: str, pattern: re.Pattern[str]) -> str | None:
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    trigger = re.search(r"\b(?:do not|don't|never|must not)\b", text, flags=re.I)
    if trigger is None:
        return matches[0].group(0).rstrip(".,;:")
    after_trigger = [match for match in matches if match.start() >= trigger.start()]
    return (after_trigger[0] if after_trigger else matches[0]).group(0).rstrip(".,;:")


def _tool_pattern_matches(pattern: ToolPattern, signature: ActionSignature) -> MatchOutcome:
    if pattern.tool != "*" and pattern.tool != signature.tool.name:
        return MatchOutcome.NOT_MATCHED
    outcomes = [
        _arg_pattern_matches(signature.tool.raw_arguments.get(key), matcher)
        for key, matcher in pattern.args.items()
    ]
    if MatchOutcome.AMBIGUOUS in outcomes:
        return MatchOutcome.AMBIGUOUS
    if MatchOutcome.NOT_MATCHED in outcomes:
        return MatchOutcome.NOT_MATCHED
    return MatchOutcome.MATCHED


def _arg_pattern_matches(value, matcher: ArgPattern) -> MatchOutcome:
    if matcher.is_empty():
        return MatchOutcome.MATCHED
    if value is None:
        return MatchOutcome.AMBIGUOUS
    text = str(value)
    if matcher.equals is not None and value != matcher.equals:
        return MatchOutcome.NOT_MATCHED
    if matcher.contains is not None and matcher.contains not in text:
        return MatchOutcome.NOT_MATCHED
    if matcher.regex is not None:
        try:
            if re.search(matcher.regex, text) is None:
                return MatchOutcome.NOT_MATCHED
        except re.error:
            return MatchOutcome.AMBIGUOUS
    if matcher.path_glob is not None and not _path_value_matches(text, matcher.path_glob):
        return MatchOutcome.NOT_MATCHED
    if matcher.mentions_path_glob is not None and not _text_mentions_path_glob(
        text, matcher.mentions_path_glob
    ):
        return MatchOutcome.NOT_MATCHED
    return MatchOutcome.MATCHED


def _path_value_matches(value: str, glob: str) -> bool:
    if fnmatch(value, glob):
        return True
    if glob.startswith("**/") and fnmatch(value, glob.removeprefix("**/")):
        return True
    if "/" not in glob and (value == glob or value.endswith(f"/{glob}")):
        return True
    return False


def _text_mentions_path_glob(text: str, glob: str) -> bool:
    prefix = glob.split("*", 1)[0].rstrip("/")
    if prefix and prefix in text:
        return True
    candidates = re.findall(r"[A-Za-z0-9_./-]+", text)
    return any(_path_value_matches(candidate, glob) for candidate in candidates)


def _target_pattern_matches(pattern: TargetPattern, target: str) -> bool:
    if pattern.kind == "path_glob":
        if fnmatch(target, pattern.value):
            return True
        if pattern.value.startswith("**/"):
            return fnmatch(target, pattern.value.removeprefix("**/"))
        return False
    return pattern.value == target


def _materialize_tool_patterns(
    *,
    contract: Contract,
    target_patterns: list[TargetPattern],
    available_actions: list[AvailableAction],
) -> list[ToolPattern]:
    actions = set(contract.semantics.actions)
    action_names = {action.name for action in available_actions}
    patterns: list[ToolPattern] = []
    if "git.push" in actions and _action_available(action_names, "git.push", "exec"):
        patterns.extend(_command_tool_patterns(r"^git\s+push(\s|$)"))
    if "git.commit" in actions and _action_available(action_names, "git.commit", "exec"):
        patterns.extend(_command_tool_patterns(r"^git\s+commit(\s|$)"))
    if "dependency.install" in actions and _action_available(
        action_names, "dependency.install", "exec"
    ):
        patterns.extend(
            _command_tool_patterns(r"^(?:npm|pnpm|yarn|uv|pip|pipx)\s+(?:install|add|sync)(\s|$)")
        )
    if {"file.write", "file.delete"}.intersection(actions):
        if _action_available(action_names, "file.write", "file.delete"):
            patterns.extend(_file_tool_patterns(_path_glob_targets(target_patterns)))
    if "web.search" in actions and _action_available(action_names, "web.search"):
        patterns.extend(
            [
                ToolPattern(tool="WebSearch"),
                ToolPattern(tool="web_search"),
                ToolPattern(tool="web.search"),
                ToolPattern(tool="search"),
            ]
        )
    if "message.send" in actions and _action_available(action_names, "message.send"):
        patterns.extend(
            [
                ToolPattern(tool="message.send"),
                ToolPattern(tool="send_message"),
                ToolPattern(tool="message"),
                ToolPattern(tool="sessions_send"),
            ]
        )
    if "email.send" in actions and _action_available(action_names, "email.send"):
        patterns.extend([ToolPattern(tool="email.send"), ToolPattern(tool="send_email")])
    if "memory.write" in actions and _action_available(action_names, "memory.write"):
        patterns.extend([ToolPattern(tool="memory.write"), ToolPattern(tool="memory_record")])
    return patterns


def _action_available(action_names: set[str], *actions: str) -> bool:
    return not action_names or bool(action_names.intersection(actions))


def _path_glob_targets(target_patterns: list[TargetPattern]) -> list[str]:
    return [pattern.value for pattern in target_patterns if pattern.kind == "path_glob"]


def _command_tool_patterns(regex: str) -> list[ToolPattern]:
    return [
        ToolPattern(tool="Bash", args={"command": ArgPattern(regex=regex)}),
        ToolPattern(tool="exec", args={"command": ArgPattern(regex=regex)}),
        ToolPattern(tool="exec", args={"cmd": ArgPattern(regex=regex)}),
        ToolPattern(tool="exec_command", args={"cmd": ArgPattern(regex=regex)}),
        ToolPattern(tool="shell", args={"command": ArgPattern(regex=regex)}),
    ]


def _file_tool_patterns(path_globs: list[str]) -> list[ToolPattern]:
    if not path_globs:
        return [
            ToolPattern(tool="Write"),
            ToolPattern(tool="Edit"),
            ToolPattern(tool="MultiEdit"),
            ToolPattern(tool="apply_patch"),
            ToolPattern(tool="write"),
            ToolPattern(tool="edit"),
            ToolPattern(tool="file.write"),
        ]
    patterns: list[ToolPattern] = []
    for glob in path_globs:
        patterns.extend(
            [
                ToolPattern(tool="Write", args={"file_path": ArgPattern(path_glob=glob)}),
                ToolPattern(tool="Edit", args={"file_path": ArgPattern(path_glob=glob)}),
                ToolPattern(tool="MultiEdit", args={"file_path": ArgPattern(path_glob=glob)}),
                ToolPattern(tool="write", args={"path": ArgPattern(path_glob=glob)}),
                ToolPattern(tool="edit", args={"path": ArgPattern(path_glob=glob)}),
                ToolPattern(tool="file.write", args={"path": ArgPattern(path_glob=glob)}),
                ToolPattern(tool="apply_patch", args={"patch": ArgPattern(mentions_path_glob=glob)}),
            ]
        )
        shell_regex = _shell_path_write_regex(glob)
        if shell_regex:
            patterns.append(ToolPattern(tool="Bash", args={"command": ArgPattern(regex=shell_regex)}))
            patterns.append(ToolPattern(tool="exec", args={"command": ArgPattern(regex=shell_regex)}))
            patterns.append(ToolPattern(tool="exec", args={"cmd": ArgPattern(regex=shell_regex)}))
    return patterns


def _shell_path_write_regex(path_glob: str) -> str | None:
    prefix = path_glob.split("*", 1)[0].rstrip("/")
    if not prefix:
        return None
    return (
        r"(^|\s)(sed|python|node|rm|mv|cp|touch|cat\s+>|tee|perl)"
        rf".*{re.escape(prefix)}/?"
    )


def _dedupe_tool_patterns(patterns: list[ToolPattern]) -> list[ToolPattern]:
    seen: set[str] = set()
    result: list[ToolPattern] = []
    for pattern in patterns:
        key = pattern.model_dump_json()
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
