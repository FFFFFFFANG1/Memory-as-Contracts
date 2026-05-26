from __future__ import annotations

import json
import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from openai import OpenAI

from memory_as_contracts.config import MacConfig, load_config
from memory_as_contracts.models import (
    ActionConstraints,
    CompiledPredicateVersion,
    Contract,
    ContractKind,
    ContractSource,
    HostActionPattern,
    Modality,
    SourceKind,
    Strength,
)
from memory_as_contracts.normalizers import (
    LifecycleNormalizer,
    NormalizationContext,
    ScopeNormalizer,
)


CONTRACT_TRIGGERS = (
    "always",
    "never",
    "do not",
    "don't",
    "must",
    "must not",
    "from now on",
    "for this project",
    "this week",
    "this session",
    "use ",
    "prefer",
    "ask me",
    "before asking",
    "without asking",
)


PERIODIC_EXTRACTION_USER_TURN_INTERVAL = 10


CONTRACT_EXTRACTION_SYSTEM_PROMPT = """
You extract agent behavior constraint candidates from user message histories and turn
them into agent contracts.

A MAC contract is a user-stated or source-stated behavioral constraint that can
legitimately influence future agent behavior. It is not merely useful context.

Count as a contract when the text creates one of these future-facing constraints:
1. Prohibition: forbids an action or class of actions.
   Example: "Do not push code without asking."
2. Requirement: requires an action, check, or condition before/after work.
   Example: "Run all tests before committing."
3. Procedure: specifies a workflow, command, or process.
   Example: "Use uv for this repo."
4. Preference: soft but behavior-shaping style or workflow guidance.
   Example: "When explaining code structure, always include a block diagram."
5. Exception: a concrete, narrower, temporary allowance that overrides a broader
   rule in a bounded scope/lifecycle.
   Example: "For this module only, you may edit generated/sandbox/**."
6. Fact: stable contextual information that may help reasoning but must not
   authorize, block, or require an action by itself.
   Example: "This repo uses torch==2.5.1."

Do not extract:
- Ordinary task content that does not constrain future behavior.
- Background facts as action-binding rules.
- Single-turn instructions for only the current answer, reply, message, or tool
  call. Ignore them by default; if an adapter intentionally keeps them, they may
  only be non-durable preferences with immediate/per-turn scope.
- Meta-statements about possible future exceptions, such as "unless a narrower
  exception says so", unless the source states a concrete allowed action and
  concrete scope.
- Duplicate paraphrases as separate contracts when they express the same rule in
  the same scope; choose the clearest wording and preserve the duplicate source
  span if useful.

Do extract separate contracts for genuine contradictions or narrower exceptions;
conflict resolution will handle them later. Return only valid JSON, no markdown.
""".strip()


ColdStartPromptBuilder = Callable[[str, SourceKind], str]


@dataclass(frozen=True)
class ExtractionContext:
    normalization: NormalizationContext
    conversation_id: str | None = None
    turn_id: str | None = None
    tool_capsule_system_prompt: str | None = None


class HeuristicContractExtractor:
    """Deterministic extractor used for tests, dry runs, and obvious rules."""

    def __init__(
        self,
        scope_normalizer: ScopeNormalizer | None = None,
        lifecycle_normalizer: LifecycleNormalizer | None = None,
    ) -> None:
        self.scope_normalizer = scope_normalizer or ScopeNormalizer()
        self.lifecycle_normalizer = lifecycle_normalizer or LifecycleNormalizer()

    def extract_online_turn(
        self,
        *,
        role: str,
        text: str,
        context: ExtractionContext,
    ) -> list[Contract]:
        if role != "user":
            return []
        return self.extract_user_turn(text=text, context=context)

    def extract_user_turn(self, *, text: str, context: ExtractionContext) -> list[Contract]:
        return self._extract(
            text=text,
            source_kind=SourceKind.USER_TURN,
            context=context,
        )

    def extract_cold_start_source(
        self,
        *,
        text: str,
        source_kind: SourceKind,
        context: ExtractionContext,
        path: str | None = None,
        fingerprint: str | None = None,
    ) -> list[Contract]:
        if source_kind == SourceKind.USER_TURN:
            raise ValueError("cold-start extraction must not use user_turn source kind")
        contracts = self._extract(
            text=text,
            source_kind=source_kind,
            context=context,
            path=path,
            fingerprint=fingerprint,
        )
        return contracts

    def _extract(
        self,
        *,
        text: str,
        source_kind: SourceKind,
        context: ExtractionContext,
        path: str | None = None,
        fingerprint: str | None = None,
    ) -> list[Contract]:
        contracts: list[Contract] = []
        for sentence in _split_candidate_sentences(text):
            if not _looks_like_contract(sentence):
                continue
            if source_kind == SourceKind.USER_TURN and _is_single_turn_instruction(sentence):
                continue
            kind, modality, strength = _classify_contract(sentence)
            source = ContractSource(
                kind=source_kind,
                conversation_id=context.conversation_id,
                turn_id=context.turn_id,
                span=sentence,
                path=path,
                fingerprint=fingerprint,
                created_at=context.normalization.current_time(),
            )
            contracts.append(
                Contract(
                    text=sentence,
                    kind=kind,
                    modality=modality,
                    strength=strength,
                    source=source,
                    scope=self.scope_normalizer.normalize(sentence, context.normalization),
                    lifecycle=self.lifecycle_normalizer.normalize(sentence, context.normalization),
                    action_constraints=_infer_action_constraints(sentence),
                )
            )
        return contracts


class JsonContractExtractor:
    """LLM-facing extractor with strict JSON validation and heuristic fallback repair."""

    def __init__(
        self,
        response_provider: Callable[[str], str],
        heuristic: HeuristicContractExtractor | None = None,
    ) -> None:
        self.response_provider = response_provider
        self.heuristic = heuristic or HeuristicContractExtractor()

    def extract_user_turn(self, *, text: str, context: ExtractionContext) -> list[Contract]:
        prompt = (
            "Extract MAC contracts as JSON objects. Return only JSON. "
            f"User text: {text}"
        )
        raw = self.response_provider(prompt)
        return self._parse_json_contracts(raw, text=text, context=context)

    def _parse_json_contracts(
        self, raw: str, *, text: str, context: ExtractionContext
    ) -> list[Contract]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("[")
            end = raw.rfind("]")
            if start == -1 or end == -1 or end <= start:
                return self.heuristic.extract_user_turn(text=text, context=context)
            payload = json.loads(raw[start : end + 1])

        if isinstance(payload, dict):
            payload = [payload]
        contracts: list[Contract] = []
        for item in payload:
            try:
                contracts.append(Contract.model_validate(item))
            except ValidationError:
                return self.heuristic.extract_user_turn(text=text, context=context)
        return contracts


class OpenAIChatResponseProvider:
    """OpenAI-compatible chat-completions response provider."""

    def __init__(
        self,
        config: MacConfig | None = None,
        *,
        system_prompt: str = CONTRACT_EXTRACTION_SYSTEM_PROMPT,
    ) -> None:
        self.config = config or load_config()
        self.system_prompt = system_prompt
        if not self.config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for live LLM extraction")
        if not self.config.llm_model:
            raise ValueError("MAC_LLM_MODEL is required for live LLM extraction")
        self.client = OpenAI(
            api_key=self.config.openai_api_key,
            base_url=self.config.openai_base_url or None,
        )

    @classmethod
    def from_env(
        cls,
        env_file: str | Path | None = None,
        *,
        system_prompt: str = CONTRACT_EXTRACTION_SYSTEM_PROMPT,
    ) -> "OpenAIChatResponseProvider":
        return cls(load_config(env_file), system_prompt=system_prompt)

    def __call__(self, prompt: str, *, system_prompt: str | None = None) -> str:
        response = self.client.chat.completions.create(
            model=self.config.llm_model or "",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt or self.system_prompt,
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""


class CandidateJsonContractExtractor:
    """LLM candidate extractor that keeps scope/lifecycle normalization local."""

    def __init__(
        self,
        response_provider: Callable[[str], str],
        *,
        scope_normalizer: ScopeNormalizer | None = None,
        lifecycle_normalizer: LifecycleNormalizer | None = None,
        cold_start_prompt_builder: ColdStartPromptBuilder | None = None,
    ) -> None:
        self.response_provider = response_provider
        self.scope_normalizer = scope_normalizer or ScopeNormalizer()
        self.lifecycle_normalizer = lifecycle_normalizer or LifecycleNormalizer()
        self.cold_start_prompt_builder = cold_start_prompt_builder or _cold_start_candidate_prompt

    def extract_online_turn(
        self,
        *,
        role: str,
        text: str,
        context: ExtractionContext,
    ) -> list[Contract]:
        if role != "user":
            return []
        return self.extract_user_turn(text=text, context=context)

    def extract_user_turn(self, *, text: str, context: ExtractionContext) -> list[Contract]:
        return self._extract_candidates(
            prompt=_user_turn_candidate_prompt(text),
            text=text,
            source_kind=SourceKind.USER_TURN,
            context=context,
        )

    def extract_cold_start_source(
        self,
        *,
        text: str,
        source_kind: SourceKind,
        context: ExtractionContext,
        path: str | None = None,
        fingerprint: str | None = None,
    ) -> list[Contract]:
        if source_kind == SourceKind.USER_TURN:
            raise ValueError("cold-start extraction must not use user_turn source kind")
        return self._extract_candidates(
            prompt=self.cold_start_prompt_builder(text, source_kind),
            text=text,
            source_kind=source_kind,
            context=context,
            path=path,
            fingerprint=fingerprint,
        )

    def _extract_candidates(
        self,
        *,
        prompt: str,
        text: str,
        source_kind: SourceKind,
        context: ExtractionContext,
        path: str | None = None,
        fingerprint: str | None = None,
    ) -> list[Contract]:
        raw = _call_response_provider(
            self.response_provider,
            prompt=prompt,
            system_prompt=_system_prompt_for_context(context),
        )
        candidates = _parse_candidate_payload(raw)
        contracts: list[Contract] = []
        for item in candidates:
            contract_text = str(item.get("text") or item.get("source_span") or "").strip()
            if not contract_text:
                continue
            if source_kind == SourceKind.USER_TURN and _is_single_turn_instruction(contract_text):
                continue
            kind = _enum_value(ContractKind, item.get("kind"), ContractKind.PREFERENCE)
            if kind == ContractKind.EXCEPTION and _is_meta_exception(contract_text):
                continue
            modality = _enum_value(Modality, item.get("modality"), _default_modality(kind))
            strength = _enum_value(Strength, item.get("strength"), Strength.SOFT)
            constraints = item.get("action_constraints") or {}
            inferred_constraints = _infer_action_constraints(contract_text)
            host_actions = _string_list(constraints.get("host_actions") or item.get("host_actions"))
            canonical_tags = _string_list(
                constraints.get("canonical_tags") or item.get("canonical_tags")
            )
            host_actions = sorted({*host_actions, *inferred_constraints.host_actions})
            canonical_tags = sorted({*canonical_tags, *inferred_constraints.canonical_tags})
            source = ContractSource(
                kind=source_kind,
                conversation_id=context.conversation_id,
                turn_id=context.turn_id,
                span=str(item.get("source_span") or contract_text),
                path=path,
                fingerprint=fingerprint,
                created_at=context.normalization.current_time(),
            )
            contracts.append(
                Contract(
                    text=contract_text,
                    kind=kind,
                    modality=modality,
                    strength=strength,
                    source=source,
                    scope=self.scope_normalizer.normalize(contract_text, context.normalization),
                    lifecycle=self.lifecycle_normalizer.normalize(
                        contract_text, context.normalization
                    ),
                    action_constraints=ActionConstraints(
                        host_actions=host_actions,
                        canonical_tags=canonical_tags,
                    ),
                )
            )
        return contracts


def _split_candidate_sentences(text: str) -> list[str]:
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip(" -\t")]
    if len(lines) > 1:
        parts = lines
    else:
        parts = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", text) if part.strip()]
    split: list[str] = []
    for part in parts:
        split.extend(_split_mixed_contract_clauses(part))
    return split


def _split_mixed_contract_clauses(text: str) -> list[str]:
    """Split compound user turns while preserving obvious leading scope."""
    text = text.strip()
    if not text:
        return []
    prefix = ""
    match = re.match(
        r"^(for\s+(?:this|the|my)\s+(?:repo|project|workspace|session|task)[^,;]*),\s+(.+)$",
        text,
        flags=re.I,
    )
    body = text
    if match:
        prefix = match.group(1).strip()
        body = match.group(2).strip()

    raw_parts = [
        part.strip(" ,")
        for part in re.split(
            r"\s*;\s*|\s*,\s+(?:and|but)\s+(?=(?:always|never|do not|don't|must|must not|prefer|use|ask)\b)",
            body,
            flags=re.I,
        )
        if part.strip(" ,")
    ]
    clauses: list[str] = []
    for part in raw_parts:
        # Drop pure current-task continuations split off from a durable rule.
        if re.match(r"^(?:now|please)\b", part, flags=re.I) and not _looks_like_contract(part):
            continue
        clause = part
        if prefix and not re.match(r"^(for|this|current|always|never)\b", clause, flags=re.I):
            clause = f"{prefix}, {clause}"
        clauses.append(clause)
    return clauses or [text]


def _looks_like_contract(text: str) -> bool:
    lower = text.lower()
    return any(trigger in lower for trigger in CONTRACT_TRIGGERS)


def _classify_contract(text: str) -> tuple[ContractKind, Modality, Strength]:
    lower = text.lower()
    if "do not" in lower or "don't" in lower or "never" in lower or "must not" in lower:
        return ContractKind.PROHIBITION, Modality.MUST_NOT, Strength.HARD
    if "must" in lower or "required" in lower or "need to" in lower:
        return ContractKind.REQUIREMENT, Modality.MUST, Strength.HARD
    if "prefer" in lower or "should" in lower:
        return ContractKind.PREFERENCE, Modality.SHOULD, Strength.SOFT
    if "use " in lower or "workflow" in lower or "process" in lower:
        return ContractKind.PROCEDURE, Modality.SHOULD, Strength.SOFT
    return ContractKind.PREFERENCE, Modality.SHOULD, Strength.SOFT


def _infer_action_constraints(text: str) -> ActionConstraints:
    lower = text.lower()
    host_actions: set[str] = set()
    tags: set[str] = set()
    if "push" in lower and any(token in lower for token in ("git", "code", "branch", "change")):
        host_actions.update({"exec", "git.push"})
        tags.update({"external_write", "publish_code"})
    if "publish" in lower:
        host_actions.add("git.push")
        tags.update({"external_write", "publish_code"})
    if "commit" in lower and "git" in lower:
        host_actions.update({"exec", "git.commit"})
        tags.update({"source_modification", "version_control"})
    if any(token in lower for token in ("edit", "write", "delete", "format", "touch")):
        host_actions.update({"file.write", "file.delete"})
        tags.update({"file_write", "source_modification", "workspace_write"})
    if any(token in lower for token in ("web search", "web-search", "browse", "browser")):
        host_actions.add("web.search")
        tags.add("network_read")
    if any(token in lower for token in ("install", "dependency", "npm", "pnpm", "uv")):
        host_actions.update({"exec", "dependency.install"})
        tags.update({"dependency_change", "shell"})
    if any(token in lower for token in ("email", "message", "messages", "slack", "send", "notify")):
        host_actions.update({"email.send", "message.send"})
        tags.update({"external_write", "notify_human"})
    if "memory" in lower:
        host_actions.add("memory.write")
        tags.add("memory_write")
    return ActionConstraints(host_actions=sorted(host_actions), canonical_tags=sorted(tags))


def _user_turn_candidate_prompt(text: str) -> str:
    return _candidate_prompt(
        text=text,
        source_kind=SourceKind.USER_TURN,
        source_instruction=(
            "This is an online user turn. Use the fixed user-turn extraction policy: "
            "durable contracts only come from repeated instructions or instructions "
            "with task, session, project, repo, file/path, component/module, "
            "organization, or global scope."
        ),
    )


def _cold_start_candidate_prompt(text: str, source_kind: SourceKind) -> str:
    return _candidate_prompt(
        text=text,
        source_kind=source_kind,
        source_instruction=(
            "This is a cold-start source. Host adapters may replace this prompt for "
            "agent-specific instruction files, memory exports, and project docs. "
            "Preserve source provenance and avoid treating stale or descriptive text "
            "as current user-turn authority."
        ),
    )


def _candidate_prompt(text: str, source_kind: SourceKind, source_instruction: str) -> str:
    return f"""
Extract candidate contracts that agent must obey in later actions from the source text.

Return exactly one JSON object with a "contracts" array. Each contract object must use:
- text: concise behavioral contract text copied or tightly paraphrased from the source
- source_span: exact source span when possible
- kind: one of prohibition, requirement, procedure, preference, exception, fact
- modality: one of MUST, MUST_NOT, SHOULD, MAY
- strength: one of hard, soft, suggestive
- action_constraints.host_actions: adapter-native actions such as exec, file.write, file.delete, git.commit, git.push, dependency.install, email.send, message.send, memory.write
- action_constraints.canonical_tags: tags such as external_write, publish_code, file_write, source_modification, workspace_write, dependency_change, notify_human, memory_write
- predicate_hints.host_action_patterns: optional deterministic action-time hints.
  Use exact string match for tool_name. If matching a tool parameter is required,
  generate parameter_regex for that argument instead of prose.

Rules:
- Source kind is {source_kind.value}. {source_instruction}
- Add durable user-turn contracts only when the text is repeated across turns/sources or clearly scopes beyond the current turn, such as task, session, project, repo, file/path, component/module, organization, or global scope.
- Facts may support reasoning, but must not bind host_actions or canonical_tags.
- Temporary/narrow allowance that overrides a broader rule must be kind "exception" and modality "MAY", but only when the source names a concrete allowed action and concrete scope. Do not extract meta exception language such as "unless a narrower exception says so" as its own exception.
- Non-obvious workflow preferences still count if they constrain future behavior.
- Merge contradictory rules into a single contract, if all fields are the same.
- For action predicates, tool_name is exact match. Parameter constraints use regex over the raw tool parameter string. 
    Example: for an exec command that pushes to git, use tool_name "exec" and parameter_regex.cmd "^git\\s+push(\\s|$)".

Return JSON shape:
{{"contracts": [{{"text": "Do not run git push until I approve it.", "source_span": "do not run git push until I approve it", "kind": "prohibition", "modality": "MUST_NOT", "strength": "hard", "action_constraints": {{"host_actions": ["git.push"], "canonical_tags": ["publish_code"]}}, "predicate_hints": {{"host_action_patterns": [{{"host_action": "git.push", "tool_name": "exec", "parameter_regex": {{"cmd": "^git\\\\s+push(\\\\s|$)"}}}}]}}}}]}}

Source text:
{text}
""".strip()


def _system_prompt_for_context(context: ExtractionContext) -> str:
    if not context.tool_capsule_system_prompt:
        return CONTRACT_EXTRACTION_SYSTEM_PROMPT
    return f"{CONTRACT_EXTRACTION_SYSTEM_PROMPT}\n\n{context.tool_capsule_system_prompt}"


def _call_response_provider(
    response_provider: Callable[[str], str],
    *,
    prompt: str,
    system_prompt: str,
) -> str:
    if _accepts_system_prompt(response_provider):
        return response_provider(prompt, system_prompt=system_prompt)  # type: ignore[call-arg]
    if system_prompt == CONTRACT_EXTRACTION_SYSTEM_PROMPT:
        return response_provider(prompt)
    return response_provider(
        "Additional system context for this extraction call:\n"
        f"{system_prompt}\n\n"
        "Extraction task prompt:\n"
        f"{prompt}"
    )


def _accepts_system_prompt(response_provider: Callable[[str], str]) -> bool:
    try:
        signature = inspect.signature(response_provider)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            return True
    parameter = signature.parameters.get("system_prompt")
    return parameter is not None and parameter.kind in {
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    }


def _parse_candidate_payload(raw: str) -> list[dict]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start_object = raw.find("{")
        end_object = raw.rfind("}")
        if start_object != -1 and end_object > start_object:
            payload = json.loads(raw[start_object : end_object + 1])
        else:
            start_array = raw.find("[")
            end_array = raw.rfind("]")
            if start_array == -1 or end_array <= start_array:
                raise
            payload = json.loads(raw[start_array : end_array + 1])
    if isinstance(payload, dict):
        contracts = payload.get("contracts", [])
    else:
        contracts = payload
    if not isinstance(contracts, list):
        raise ValueError("candidate payload must contain a contracts array")
    return [item for item in contracts if isinstance(item, dict)]


def _enum_value(enum_type, value, default):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return default


def _default_modality(kind: ContractKind) -> Modality:
    if kind == ContractKind.PROHIBITION:
        return Modality.MUST_NOT
    if kind in {ContractKind.REQUIREMENT, ContractKind.PROCEDURE}:
        return Modality.MUST
    if kind == ContractKind.EXCEPTION:
        return Modality.MAY
    return Modality.SHOULD


def _string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _compiled_predicates_from_hints(
    *,
    item: dict,
    host_actions: list[str],
    canonical_tags: list[str],
) -> CompiledPredicateVersion | None:
    hints = item.get("predicate_hints") or {}
    if not isinstance(hints, dict):
        return None
    patterns = hints.get("host_action_patterns") or []
    if not isinstance(patterns, list):
        return None
    host_patterns: list[HostActionPattern] = []
    for pattern in patterns:
        if not isinstance(pattern, dict):
            continue
        tool_name = _optional_string(pattern.get("tool_name"))
        action = _optional_string(pattern.get("host_action") or pattern.get("action"))
        if action is None:
            action = _preferred_host_action(host_actions, tool_name)
        parameter_regex = _string_dict(pattern.get("parameter_regex"))
        host_patterns.append(
            HostActionPattern(
                action=action,
                tool_name=tool_name,
                program=_optional_string(pattern.get("program")),
                subcommand=_optional_string(pattern.get("subcommand")),
                parameter_regex=parameter_regex,
            )
        )
    if not host_patterns:
        return None
    return CompiledPredicateVersion(
        host_action_patterns=host_patterns,
        canonical_tags=canonical_tags,
    )


def _preferred_host_action(host_actions: list[str], tool_name: str | None) -> str:
    if not host_actions:
        return "*"
    if tool_name == "exec":
        for action in host_actions:
            if action != "exec":
                return action
    for action in host_actions:
        if action == tool_name:
            return action
    return host_actions[0]


def _optional_string(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_dict(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(item)
        for key, item in value.items()
        if key is not None and item is not None and str(item)
    }


def _is_meta_exception(text: str) -> bool:
    lower = text.lower()
    return "narrower" in lower and "exception" in lower and "you may" not in lower


def _is_single_turn_instruction(text: str) -> bool:
    lower = text.lower()
    markers = (
        "this answer",
        "this reply",
        "this response",
        "this message",
        "this turn",
        "current answer",
        "current reply",
        "current response",
        "current message",
        "current turn",
        "in your answer",
        "in this answer",
        "in your reply",
        "in this reply",
    )
    return any(marker in lower for marker in markers)
