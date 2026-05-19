from __future__ import annotations

import json
import re

from openai import BadRequestError, OpenAI, OpenAIError
from pydantic import ValidationError

from memory_use_contracts.config import Settings
from memory_use_contracts.models import (
    ActionClass,
    Contract,
    ContractType,
    Modality,
    Scope,
    Source,
    SourceKind,
    Strength,
)


class ContractExtractionError(RuntimeError):
    pass


SYSTEM_PROMPT = """You extract Memory Use Contracts for coding agents.
Return only JSON with a top-level "contracts" array.
Each item must include text, type, modality, source.span, scope, action_classes,
strength, confirmation, and confidence.
Allowed type values: prohibition, requirement, procedure, preference, exception, fact.
Allowed action_classes: edit_file, delete_file, run_command, format_file,
install_dependency, commit, push, update_docs.
Fact contracts must use an empty action_classes array.
Do not invent unsupported facts. Keep source.span as an exact substring when possible.
Use confirmation=not_required unless the text explicitly says to ask, confirm,
or get approval. Use required_to_override for "unless explicitly asked" style
prohibitions.
"""


class ContractExtractor:
    def __init__(self, settings: Settings):
        self.settings = settings

    def extract(
        self,
        text: str,
        source_kind: SourceKind,
        workspace: str = "default",
    ) -> list[Contract]:
        if not self.settings.openai_api_key:
            raise ContractExtractionError("OPENAI_API_KEY is required for Standard extraction")

        client = OpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Source kind: {source_kind.value}\n"
                    f"Workspace: {workspace}\n"
                    f"Raw memory/event:\n{text}"
                ),
            },
        ]
        try:
            response = client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0,
            )
        except BadRequestError as exc:
            if "response_format" not in str(exc) and "json_object" not in str(exc):
                raise ContractExtractionError(_format_openai_error(exc)) from exc
            try:
                response = client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=messages,
                    temperature=0,
                )
            except OpenAIError as retry_exc:
                raise ContractExtractionError(_format_openai_error(retry_exc)) from retry_exc
        except OpenAIError as exc:
            raise ContractExtractionError(_format_openai_error(exc)) from exc
        content = response.choices[0].message.content or "{}"
        return parse_extraction_json(content, source_kind=source_kind, workspace=workspace)


def parse_extraction_json(
    content: str,
    source_kind: SourceKind,
    workspace: str = "default",
) -> list[Contract]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ContractExtractionError(f"Extractor returned invalid JSON: {exc}") from exc

    items = data.get("contracts")
    if not isinstance(items, list):
        raise ContractExtractionError('Extractor JSON must include a "contracts" array')

    contracts: list[Contract] = []
    for item in items:
        try:
            source_data = item.get("source") or {}
            scope_data = _normalize_scope_data(item.get("scope"), workspace)
            if not scope_data["path_globs"]:
                scope_data["path_globs"] = _infer_path_globs(item["text"])
            contract_type = ContractType(_normalize_type(item["type"]))
            contract = Contract(
                text=item["text"],
                type=contract_type,
                modality=Modality(_normalize_modality(item.get("modality"), contract_type)),
                source=Source(
                    kind=source_kind,
                    span=source_data.get("span") or item["text"],
                ),
                scope=Scope(
                    workspace=scope_data["workspace"],
                    path_globs=scope_data["path_globs"],
                    task=scope_data.get("task"),
                ),
                action_classes=[
                    ActionClass(_normalize_action_class(value))
                    for value in item.get("action_classes", [])
                ],
                strength=Strength(
                    _normalize_strength(
                        item.get("strength"),
                        text=item["text"],
                        contract_type=contract_type,
                    )
                ),
                confirmation=_normalize_confirmation(
                    item.get("confirmation"),
                    text=item["text"],
                    contract_type=contract_type,
                ),
                confidence=_normalize_confidence(item.get("confidence", 1.0)),
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ContractExtractionError(f"Invalid extracted contract: {item}") from exc
        contracts.append(contract)
    return contracts


def _format_openai_error(exc: OpenAIError) -> str:
    return (
        "LLM extraction failed via OpenAI-compatible endpoint: "
        f"{exc.__class__.__name__}: {exc}"
    )


def _normalize_scope_data(scope: object, workspace: str) -> dict:
    if not isinstance(scope, dict):
        return {"workspace": workspace, "path_globs": [], "task": None}
    path_globs = scope.get("path_globs") or []
    if isinstance(path_globs, str):
        path_globs = [path_globs]
    return {
        "workspace": scope.get("workspace") or workspace,
        "path_globs": path_globs,
        "task": scope.get("task"),
    }


def _infer_path_globs(text: str) -> list[str]:
    candidates = re.findall(r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+/\*\*|[A-Za-z0-9_.-]+/\*)", text)
    return sorted(set(candidates))


def _normalize_type(value: object) -> str:
    text = str(value or "").lower()
    aliases = {
        "rule": "requirement",
        "constraint": "requirement",
        "forbid": "prohibition",
        "forbidden": "prohibition",
        "ban": "prohibition",
        "instruction": "procedure",
        "process": "procedure",
        "preference": "preference",
        "exception": "exception",
        "fact": "fact",
    }
    return aliases.get(text, text)


def _normalize_modality(value: object, contract_type: ContractType) -> str:
    text = str(value or "").upper()
    aliases = {
        "MUST": "MUST",
        "REQUIRED": "MUST",
        "SHALL": "MUST",
        "MUST_NOT": "MUST_NOT",
        "MUST NOT": "MUST_NOT",
        "DO_NOT": "MUST_NOT",
        "PROHIBITED": "MUST_NOT",
        "SHOULD": "SHOULD",
        "PREFER": "SHOULD",
        "MAY": "MAY",
    }
    if text in aliases:
        return aliases[text]
    if contract_type == ContractType.PROHIBITION:
        return "MUST_NOT"
    if contract_type in {ContractType.REQUIREMENT, ContractType.PROCEDURE}:
        return "MUST"
    if contract_type == ContractType.PREFERENCE:
        return "SHOULD"
    return "MAY"


def _normalize_strength(
    value: object,
    text: str = "",
    contract_type: ContractType | None = None,
) -> str:
    lowered_text = text.lower()
    if contract_type == ContractType.PROHIBITION and any(
        marker in lowered_text for marker in ("do not", "don't", "never", "must not")
    ):
        return "hard"

    text = str(value or "").lower()
    aliases = {
        "strict": "hard",
        "strong": "hard",
        "required": "hard",
        "mandatory": "hard",
        "hard": "hard",
        "soft": "soft",
        "weak": "suggestive",
        "suggestion": "suggestive",
        "suggestive": "suggestive",
    }
    return aliases.get(text, "soft")


def _normalize_confirmation(
    value: object,
    text: str = "",
    contract_type: ContractType | None = None,
) -> str:
    lowered_text = text.lower()
    if "unless explicitly asked" in lowered_text or "unless explicitly confirmed" in lowered_text:
        return "required_to_override"
    if (
        "ask before" in lowered_text
        or "confirm before" in lowered_text
        or "get approval" in lowered_text
        or "requires confirmation" in lowered_text
    ):
        return "required"

    text = str(value or "").lower()
    aliases = {
        "none": "not_required",
        "no": "not_required",
        "false": "not_required",
        "not_required": "not_required",
        "required": "required",
        "yes": "required",
        "true": "required",
        "explicit": "required_to_override",
        "required_to_override": "required_to_override",
        "explicit_user_confirmation": "required_to_override",
    }
    normalized = aliases.get(text, "not_required")
    if normalized == "required" and contract_type == ContractType.PROHIBITION:
        return "not_required"
    return normalized


def _normalize_action_class(value: object) -> str:
    text = str(value or "").lower()
    aliases = {
        "write_file": "edit_file",
        "modify_file": "edit_file",
        "remove_file": "delete_file",
        "shell": "run_command",
        "shell_command": "run_command",
        "command": "run_command",
        "install": "install_dependency",
        "dependency_install": "install_dependency",
        "git_commit": "commit",
        "git_push": "push",
        "docs": "update_docs",
    }
    return aliases.get(text, text)


def _normalize_confidence(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").lower()
    aliases = {
        "high": 0.9,
        "medium": 0.6,
        "low": 0.3,
    }
    if text in aliases:
        return aliases[text]
    try:
        return float(text)
    except ValueError:
        return 1.0
