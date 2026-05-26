from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from memory_as_contracts.models import HostActionPattern, TargetPattern


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "target",
}

LOCKFILE_PATTERNS = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
    "go.sum",
}

ENV_SECRET_PATTERNS = {
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_ed25519",
    "secrets.*",
    "credentials.*",
}

CONFIG_PATTERNS = {
    "pyproject.toml",
    "package.json",
    "tsconfig.json",
    "vite.config.*",
    "next.config.*",
    "ruff.toml",
    "mypy.ini",
    ".eslintrc*",
    ".prettierrc*",
}

MANIFEST_PATTERNS = {
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "composer.json",
}

GENERATED_PATTERNS = {
    "generated/**",
    "dist/**",
    "build/**",
    "target/**",
    "*.generated.*",
    "*.pb.*",
}

SPECIAL_FILE_CATEGORIES = {
    "lockfile": LOCKFILE_PATTERNS,
    "env_secret": ENV_SECRET_PATTERNS,
    "config": CONFIG_PATTERNS,
    "manifest": MANIFEST_PATTERNS,
    "generated": GENERATED_PATTERNS,
}

CATEGORY_TERMS = {
    "lockfile": ("lockfile", "lockfiles", "lock file", "lock files"),
    "env_secret": ("env file", "env files", ".env", "secret", "secrets", "credential"),
    "config": ("config file", "config files", "configuration file", "configuration files"),
    "manifest": ("manifest", "manifest file", "manifest files"),
    "generated": ("generated", "build output", "generated file", "generated files"),
}

COMMAND_PATTERNS: dict[tuple[str, str | None], tuple[str, str]] = {
    ("git", "push"): ("git.push", r"^git\s+push(\s|$)"),
    ("git", "commit"): ("git.commit", r"^git\s+commit(\s|$)"),
    ("git", "merge"): ("exec", r"^git\s+merge(\s|$)"),
    ("git", "rebase"): ("exec", r"^git\s+rebase(\s|$)"),
    ("git", "checkout"): ("exec", r"^git\s+checkout(\s|$)"),
    ("git", "reset"): ("exec", r"^git\s+reset(\s|$)"),
    ("git", "tag"): ("exec", r"^git\s+tag(\s|$)"),
    ("git", "clean"): ("exec", r"^git\s+clean(\s|$)"),
    ("git", "pull"): ("exec", r"^git\s+pull(\s|$)"),
    ("git", "fetch"): ("exec", r"^git\s+fetch(\s|$)"),
    ("npm", "install"): ("dependency.install", r"^npm\s+install(\s|$)"),
    ("npm", "publish"): ("exec", r"^npm\s+publish(\s|$)"),
    ("npm", "version"): ("exec", r"^npm\s+version(\s|$)"),
    ("pnpm", "install"): ("dependency.install", r"^pnpm\s+install(\s|$)"),
    ("pnpm", "add"): ("dependency.install", r"^pnpm\s+add(\s|$)"),
    ("pnpm", "publish"): ("exec", r"^pnpm\s+publish(\s|$)"),
    ("yarn", "install"): ("dependency.install", r"^yarn\s+install(\s|$)"),
    ("yarn", "add"): ("dependency.install", r"^yarn\s+add(\s|$)"),
    ("yarn", "publish"): ("exec", r"^yarn\s+publish(\s|$)"),
    ("uv", "sync"): ("dependency.install", r"^uv\s+sync(\s|$)"),
    ("uv", "add"): ("dependency.install", r"^uv\s+add(\s|$)"),
    ("uv", "remove"): ("dependency.install", r"^uv\s+remove(\s|$)"),
    ("uv", "pip"): ("dependency.install", r"^uv\s+pip\s+install(\s|$)"),
    ("pip", "install"): ("dependency.install", r"^pip\s+install(\s|$)"),
    ("pip", "uninstall"): ("dependency.install", r"^pip\s+uninstall(\s|$)"),
    ("poetry", "install"): ("dependency.install", r"^poetry\s+install(\s|$)"),
    ("poetry", "add"): ("dependency.install", r"^poetry\s+add(\s|$)"),
    ("poetry", "publish"): ("exec", r"^poetry\s+publish(\s|$)"),
    ("docker", "build"): ("exec", r"^docker\s+build(\s|$)"),
    ("docker", "run"): ("exec", r"^docker\s+run(\s|$)"),
    ("docker", "push"): ("exec", r"^docker\s+push(\s|$)"),
    ("docker", "compose"): ("exec", r"^docker\s+compose\s+up(\s|$)"),
    ("kubectl", "apply"): ("exec", r"^kubectl\s+apply(\s|$)"),
    ("kubectl", "delete"): ("exec", r"^kubectl\s+delete(\s|$)"),
    ("kubectl", "rollout"): ("exec", r"^kubectl\s+rollout(\s|$)"),
    ("terraform", "apply"): ("exec", r"^terraform\s+apply(\s|$)"),
    ("terraform", "destroy"): ("exec", r"^terraform\s+destroy(\s|$)"),
    ("terraform", "plan"): ("exec", r"^terraform\s+plan(\s|$)"),
    ("pytest", None): ("exec", r"^pytest(\s|$)"),
    ("ruff", None): ("exec", r"^ruff(\s|$)"),
    ("mypy", None): ("exec", r"^mypy(\s|$)"),
    ("cargo", "test"): ("exec", r"^cargo\s+test(\s|$)"),
    ("go", "test"): ("exec", r"^go\s+test(\s|$)"),
    ("rm", None): ("exec", r"^rm(\s|$)"),
    ("mv", None): ("exec", r"^mv(\s|$)"),
    ("cp", None): ("exec", r"^cp(\s|$)"),
    ("chmod", None): ("exec", r"^chmod(\s|$)"),
    ("chown", None): ("exec", r"^chown(\s|$)"),
    ("curl", None): ("exec", r"^curl(\s|$)"),
    ("wget", None): ("exec", r"^wget(\s|$)"),
    ("gh", None): ("exec", r"^gh(\s|$)"),
}

RELATIVE_PATH_PATTERN = re.compile(
    r"\b(?:[A-Za-z0-9_.-]+/)+(?:[A-Za-z0-9_.-]+)\."
    r"(?:py|js|jsx|ts|tsx|md|json|toml|yaml|yml|txt|lock|rs|go|java|c|cc|cpp|h|css|html|sh)\b"
)


@dataclass
class GroundingCache:
    workspace: Path | None = None
    max_files: int = 5000
    _files_by_name: dict[str, list[str]] = field(default_factory=dict, init=False)
    _known_files: set[str] = field(default_factory=set, init=False)
    _scanned: bool = field(default=False, init=False)

    @classmethod
    def from_workspace(cls, workspace: str | None) -> "GroundingCache":
        if not workspace:
            return cls()
        return cls(workspace=Path(workspace).expanduser().resolve(strict=False))

    def ground_host_patterns(
        self,
        *,
        text: str,
        hint_patterns: list[HostActionPattern],
        action_names: set[str],
    ) -> list[HostActionPattern]:
        result: list[HostActionPattern] = []
        for pattern in hint_patterns:
            result.extend(self._ground_hint_pattern(pattern, action_names))
        result.extend(self._patterns_from_text(text, action_names))
        return _dedupe_host_patterns(result)

    def ground_targets(
        self,
        *,
        text: str,
        hint_targets: list[TargetPattern],
        scope_globs: list[str],
    ) -> list[TargetPattern]:
        values: list[str] = []
        for pattern in hint_targets:
            if pattern.kind == "path_glob":
                values.extend(self.ground_path(pattern.value))
            else:
                values.append(pattern.value)
        for value in scope_globs:
            values.extend(self.ground_path(value))
        values.extend(_relative_paths(text))
        category = self.category_patterns(text)
        if category:
            values.extend(category)
        return [TargetPattern(kind="path_glob", value=value) for value in _dedupe(values)]

    def ground_path(self, value: str) -> list[str]:
        clean = value.strip().strip("`'\"").rstrip(".,;:")
        if not clean:
            return []
        if "*" in clean or "/" in clean:
            return [clean]
        if "." not in clean:
            return [clean]
        matches = self.find_by_name(clean)
        if len(matches) == 1:
            return matches
        return [f"**/{clean}"]

    def category_patterns(self, text: str) -> list[str]:
        lower = text.lower()
        categories = [
            name
            for name, terms in CATEGORY_TERMS.items()
            if any(term in lower for term in terms)
        ]
        values: list[str] = []
        for category in categories:
            values.extend(self.existing_special_files(category))
            values.extend(SPECIAL_FILE_CATEGORIES[category])
        return _dedupe(values)

    def existing_special_files(self, category: str) -> list[str]:
        self._scan()
        patterns = SPECIAL_FILE_CATEGORIES.get(category, set())
        return sorted(
            path
            for path in self._known_files
            if any(_path_matches(path, pattern) for pattern in patterns)
        )

    def find_by_name(self, filename: str) -> list[str]:
        self._scan()
        return sorted(self._files_by_name.get(filename, []))

    def _ground_hint_pattern(
        self,
        pattern: HostActionPattern,
        action_names: set[str],
    ) -> list[HostActionPattern]:
        if not _valid_parameter_regex(pattern):
            return []
        phrase = " ".join(str(value) for value in pattern.parameter_regex.values())
        command = _command_from_text(f"{pattern.action} {pattern.program or ''} {pattern.subcommand or ''} {phrase}")
        if command is not None:
            return [_command_pattern(command, action_names)]
        action = _valid_action(pattern.action, action_names)
        if action is None:
            return []
        return [pattern.model_copy(update={"action": action})]

    def _patterns_from_text(self, text: str, action_names: set[str]) -> list[HostActionPattern]:
        patterns: list[HostActionPattern] = []
        lower = text.lower()
        for command in _commands_from_text(lower):
            patterns.append(_command_pattern(command, action_names))
        return patterns

    def _scan(self) -> None:
        if self._scanned:
            return
        self._scanned = True
        if self.workspace is None or not self.workspace.exists():
            return
        count = 0
        for path in self.workspace.rglob("*"):
            if count >= self.max_files:
                break
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(self.workspace).as_posix()
            except ValueError:
                continue
            self._known_files.add(rel)
            self._files_by_name.setdefault(path.name, []).append(rel)
            count += 1


def _command_pattern(command: tuple[str, str | None], action_names: set[str]) -> HostActionPattern:
    preferred, regex = COMMAND_PATTERNS[command]
    action = preferred if preferred in action_names else "exec"
    program, subcommand = command
    return HostActionPattern(
        action=action,
        tool_name="exec",
        program=program,
        subcommand=subcommand,
        parameter_regex={"cmd": regex},
    )


def _commands_from_text(text: str) -> list[tuple[str, str | None]]:
    return [command for command in COMMAND_PATTERNS if _command_mentioned(text, command)]


def _command_from_text(text: str) -> tuple[str, str | None] | None:
    lower = text.lower()
    for command in COMMAND_PATTERNS:
        if _command_mentioned(lower, command):
            return command
    return None


def _command_mentioned(text: str, command: tuple[str, str | None]) -> bool:
    program, subcommand = command
    if subcommand is None:
        return re.search(rf"(^|\W){re.escape(program)}(\W|$)", text) is not None
    return re.search(rf"(^|\W){re.escape(program)}\s+{re.escape(subcommand)}(\W|$)", text) is not None


def _valid_action(action: str, action_names: set[str]) -> str | None:
    if not action_names or action in action_names:
        return action
    if action == "exec":
        return "exec"
    return None


def _valid_parameter_regex(pattern: HostActionPattern) -> bool:
    for regex in pattern.parameter_regex.values():
        try:
            re.compile(regex)
        except re.error:
            return False
    return True


def _relative_paths(text: str) -> list[str]:
    return [match.group(0).rstrip(".,;:") for match in RELATIVE_PATH_PATTERN.finditer(text)]


def _path_matches(path: str, pattern: str) -> bool:
    regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return re.match(regex, path) is not None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_host_patterns(patterns: list[HostActionPattern]) -> list[HostActionPattern]:
    seen: set[tuple] = set()
    result: list[HostActionPattern] = []
    for pattern in patterns:
        key = (
            pattern.action,
            pattern.tool_name,
            pattern.program,
            pattern.subcommand,
            tuple(sorted(pattern.parameter_regex.items())),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(pattern)
    return result
