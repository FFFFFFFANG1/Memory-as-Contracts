from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from memory_as_contracts.models import TargetPattern


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
