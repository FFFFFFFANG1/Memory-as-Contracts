from __future__ import annotations

import re
from fnmatch import fnmatch

from memory_as_contracts.grounding_cache import GroundingCache
from memory_as_contracts.models import (
    ActionSignature,
    ArgPattern,
    Contract,
    MatchOutcome,
    RulePatternVersion,
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
        *,
        version: str = "PV-001",
        refines: str | None = None,
    ) -> RulePatternVersion:
        tool_patterns = list(contract.tool_patterns)
        tags = set(contract.semantics.tags)
        grounding = self._grounding_cache(contract)
        path_globs = grounding.ground_paths(
            text=contract.text,
            hint_paths=_path_hints(contract.text, self),
            scope_globs=contract.scope.path_globs,
        )
        tool_patterns = _ground_seed_patterns(
            contract=contract,
            tool_patterns=tool_patterns,
            path_globs=path_globs,
        )

        return RulePatternVersion(
            contract_id=contract.id,
            version=version,
            tool_patterns=_dedupe_tool_patterns(tool_patterns),
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
            return MatchOutcome.NOT_MATCHED
        return (
            MatchOutcome.MATCHED
            if any(_tool_pattern_matches(pattern, signature) for pattern in predicate.tool_patterns)
            else MatchOutcome.NOT_MATCHED
        )


def _path_hints(text: str, compiler: PolicyCompiler) -> list[str]:
    lower = text.lower()
    relative_path = compiler.relative_path_pattern.search(text)
    if relative_path:
        return [relative_path.group(0).rstrip(".,;:")]
    path_match = compiler.path_pattern.search(text)
    if path_match:
        return [(path_match.group(1) or path_match.group(2)).rstrip(".,;:")]
    glob_match = compiler.glob_pattern.search(text)
    if glob_match:
        return [glob_match.group(1).rstrip(".,;:")]
    bare_file = _selected_bare_file_target(text, compiler.bare_file_pattern)
    if bare_file and any(token in lower for token in ("edit", "write", "delete", "touch", "read")):
        return [bare_file]
    if "generated" in lower and any(token in lower for token in ("edit", "write", "touch")):
        return ["generated/**"]
    return []


def _selected_bare_file_target(text: str, pattern: re.Pattern[str]) -> str | None:
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    trigger = re.search(r"\b(?:do not|don't|never|must not)\b", text, flags=re.I)
    if trigger is None:
        return matches[0].group(0).rstrip(".,;:")
    after_trigger = [match for match in matches if match.start() >= trigger.start()]
    return (after_trigger[0] if after_trigger else matches[0]).group(0).rstrip(".,;:")


def _tool_pattern_matches(pattern: ToolPattern, signature: ActionSignature) -> bool:
    if pattern.tool != "*" and pattern.tool != signature.tool.name:
        return False
    return all(
        _arg_pattern_matches(signature.tool.raw_arguments.get(key), matcher)
        for key, matcher in pattern.args.items()
    )


def _arg_pattern_matches(value, matcher: ArgPattern) -> bool:
    if matcher.is_empty():
        return True
    if value is None:
        return False
    text = str(value)
    if matcher.equals is not None and value != matcher.equals:
        return False
    if matcher.contains is not None and matcher.contains not in text:
        return False
    if matcher.regex is not None:
        try:
            if re.search(matcher.regex, text) is None:
                return False
        except re.error:
            return False
    if matcher.path_glob is not None and not _path_value_matches(text, matcher.path_glob):
        return False
    if matcher.mentions_path_glob is not None and not _text_mentions_path_glob(
        text, matcher.mentions_path_glob
    ):
        return False
    return True


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


def _ground_seed_patterns(
    *,
    contract: Contract,
    tool_patterns: list[ToolPattern],
    path_globs: list[str],
) -> list[ToolPattern]:
    actions = set(contract.semantics.actions)
    patterns: list[ToolPattern] = []
    for pattern in tool_patterns:
        if pattern.args:
            grounded = _ground_pattern_paths(pattern, path_globs)
            patterns.extend(grounded or [pattern])
            continue
        if path_globs and {"file.write", "file.delete"}.intersection(actions):
            arg_name = _path_argument_name(pattern.tool)
            if arg_name is not None:
                for path_glob in path_globs:
                    matcher = (
                        ArgPattern(mentions_path_glob=path_glob)
                        if pattern.tool == "apply_patch"
                        else ArgPattern(path_glob=path_glob)
                    )
                    patterns.append(
                        ToolPattern(tool=pattern.tool, args={arg_name: matcher})
                    )
                continue
        command_regex = _semantic_command_regex(actions)
        arg_name = _command_argument_name(pattern.tool)
        if command_regex is not None and arg_name is not None:
            patterns.append(
                ToolPattern(
                    tool=pattern.tool,
                    args={arg_name: ArgPattern(regex=command_regex)},
                )
            )
            continue
        patterns.append(pattern)
    return patterns


def _ground_pattern_paths(
    pattern: ToolPattern,
    path_globs: list[str],
) -> list[ToolPattern]:
    if not path_globs:
        return []
    result: list[ToolPattern] = []
    for argument, matcher in pattern.args.items():
        if matcher.path_glob is None and matcher.mentions_path_glob is None:
            continue
        for path_glob in path_globs:
            replacement = matcher.model_copy(
                update={
                    "path_glob": (
                        path_glob if matcher.path_glob is not None else None
                    ),
                    "mentions_path_glob": (
                        path_glob
                        if matcher.mentions_path_glob is not None
                        else None
                    ),
                }
            )
            args = dict(pattern.args)
            args[argument] = replacement
            result.append(pattern.model_copy(update={"args": args}))
    return result


def _path_argument_name(tool: str) -> str | None:
    if tool in {"Write", "Edit", "MultiEdit"}:
        return "file_path"
    if tool in {"write", "edit", "file.write"}:
        return "path"
    if tool == "apply_patch":
        return "patch"
    return None


def _command_argument_name(tool: str) -> str | None:
    if tool == "Bash":
        return "command"
    if tool == "exec_command":
        return "cmd"
    if tool in {"exec", "shell"}:
        return "command"
    return None


def _semantic_command_regex(actions: set[str]) -> str | None:
    if "git.push" in actions:
        return r"^git\s+push(\s|$)"
    if "git.commit" in actions:
        return r"^git\s+commit(\s|$)"
    if "dependency.install" in actions:
        return r"^(?:npm|pnpm|yarn|uv|pip|pipx)\s+(?:install|add|sync)(\s|$)"
    return None


def _dedupe_tool_patterns(patterns: list[ToolPattern]) -> list[ToolPattern]:
    seen: set[str] = set()
    result: list[ToolPattern] = []
    for pattern in patterns:
        key = pattern.model_dump_json()
        if key not in seen:
            seen.add(key)
            result.append(pattern)
    return result
