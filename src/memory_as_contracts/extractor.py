from __future__ import annotations

import json
import inspect
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from openai import APITimeoutError, OpenAI

from memory_as_contracts.config import MacConfig, load_config
from memory_as_contracts.logging_config import log_event
from memory_as_contracts.models import (
    ArgPattern,
    Contract,
    ContractKind,
    ContractSource,
    ContractStatus,
    Lifecycle,
    LifecycleType,
    Modality,
    RuleEffect,
    RuleSemantics,
    RuleValidity,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
    ToolPattern,
    ValidatorEnforcementShape,
)
from memory_as_contracts.normalizers import (
    LifecycleNormalizer,
    NormalizationContext,
    ScopeNormalizer,
)


LOGGER = logging.getLogger(__name__)


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
    "before ",
    "before asking",
    "without asking",
)


PERIODIC_EXTRACTION_USER_TURN_INTERVAL = 10
LLM_MAX_ATTEMPTS = 3


class LLMCallError(RuntimeError):
    def __init__(self, *, code: str, message: str, attempts: int) -> None:
        super().__init__(message)
        self.code = code
        self.attempts = attempts

    @classmethod
    def timeout(cls, *, attempts: int = LLM_MAX_ATTEMPTS) -> "LLMCallError":
        return cls(
            code="llm_timeout",
            message=f"LLM request timed out after {attempts} attempts",
            attempts=attempts,
        )

    def as_dict(self) -> dict[str, str | int]:
        return {
            "code": self.code,
            "message": str(self),
            "attempts": self.attempts,
        }


CONTRACT_EXTRACTION_SYSTEM_PROMPT = """
You turn source text (user messages, project docs, or memory exports) into durable
behavioral contracts for an AI agent. A contract governs the agent's FUTURE actions; it is
never one-off task content. The source text and any tool capsules are given in the user
message.

# What a MAC contract is
A MAC contract is a user-stated or source-stated hard behavioral constraint that can
legitimately gate future agent behavior at runtime. Recognize these kinds:
- prohibition: forbids an action or class of actions. ("Do not push code without asking.")
- requirement: requires an action, check, or condition before/after work. ("Run all tests before committing.")
- procedure: specifies a workflow, command, or process. ("Use uv for this repo.")
- exception: a concrete, narrower, temporary allowance overriding a broader rule in a bounded scope. ("For this module only, you may edit generated/sandbox/**.")

# Durability filter
Extract only durable constraints. A user-turn instruction is durable when it is repeated,
or scoped beyond the current turn (global, session, project, or module within one project).
Do not extract:
- Soft preferences, style guidance, personal taste, or response-format habits unless they are phrased as mandatory runtime constraints.
- One-off instructions meant only for the current answer, reply, message, or tool call.
- Ordinary task content, or background facts treated as action-binding rules.
- Meta-statements about possible future exceptions (e.g. "unless a narrower exception says so") unless a concrete allowed action and scope are named.
- Duplicate paraphrases of a rule already captured in the same scope; keep the clearest wording.

# Your task
Read the user message history and return every durable contract it states. Inspect each bullet of a
list independently. You decide the contract text, scope, validity deadline, semantics,
enforcement shape, and tool patterns. The runtime will only schema-check your fields; it
will not infer missing tool patterns or enforcement shape from the contract text.

# Output fields (return ONLY valid JSON, no markdown)
Return one object: {"contracts": [<contract>, ...]}. Each <contract> has:
- text: concise contract text, copied or tightly paraphrased from the source.
- effect: one of deny, allow, require.
- scope: {"level": one of global|workspace|session|path, ...}.
  Use global for user-wide rules, workspace with {"workspace": "..."} for the current workspace,
  session for current-session rules, and path with {"workspace": "...", "path": "folder-or-file"}
  for folder/file scoped rules.
- valid_until: ISO-8601 timestamp with timezone, or null when the rule is valid until revoked.
- semantics: {"actions": [...], "tags": [...]} — retrieval/dedup/relation labels only; they do not enforce anything.
- validator_enforcement_shape: one of check_only, check_update.
- check_patterns: native tool patterns for pending actions, using only tool names and arg names from the user-provided tool capsules.
- update_patterns: native tool patterns for committed actions that update validator state.
- state_fields: state keys maintained by check_update validators.

# Enforcement plan
Choose the lightest enforcement shape that can represent the contract. 
- check_only: action-time enforcement that can be decided from the pending action plus a bounded action-log lookup. Requires non-empty check_patterns; update_patterns and state_fields must be [].
- check_update: stateful action-time enforcement. Use only when enforcement needs maintained state across committed actions. Requires non-empty check_patterns, non-empty update_patterns, and explicit state_fields.
- Do not invent tool names or argument names. If a statement cannot be represented as a runtime validation hook over the provided native tool capsules, do not output it as a MAC contract.

# Consistency
- Before output, internally resolve duplicates, conflicts, superseded instructions, and
  narrower exceptions; output only each contract's final effective form for this user
  history, not the intermediate reasoning or discarded versions.

# Output shape
{"contracts": [{"text": "...", "effect": "require", "scope": {"level": "workspace", "workspace": "..."}, "valid_until": null, "semantics": {"actions": ["..."], "tags": ["..."]}, "validator_enforcement_shape": "check_only", "check_patterns": [{"tool": "<native tool name>", "args": {"<arg name>": {"regex": "..."}}}], "update_patterns": [], "state_fields": []}]}
""".strip()


ColdStartPromptBuilder = Callable[[str, SourceKind], str]


@dataclass(frozen=True)
class ExtractionContext:
    normalization: NormalizationContext
    session_id: str | None = None
    conversation_id: str | None = None
    turn_id: str | None = None
    tool_capsule_system_prompt: str | None = None
    similar_rules_system_prompt: str | None = None


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
            if kind == ContractKind.PREFERENCE or strength == Strength.SOFT:
                continue
            source = ContractSource(
                kind=source_kind,
                conversation_id=context.conversation_id,
                turn_id=context.turn_id,
                path=path,
                fingerprint=fingerprint,
                metadata=_source_metadata(context) if source_kind == SourceKind.USER_TURN else {},
                created_at=context.normalization.current_time(),
            )
            scope = self.scope_normalizer.normalize(sentence, context.normalization)
            semantics = _infer_semantics(sentence)
            validator_shape = _infer_validator_enforcement_shape(sentence)
            check_patterns = _infer_check_patterns(sentence, validator_shape) or _infer_tool_patterns(
                sentence,
                [],
            )
            contracts.append(
                Contract(
                    text=sentence,
                    kind=kind,
                    modality=modality,
                    strength=strength,
                    source=source,
                    scope=scope,
                    lifecycle=self.lifecycle_normalizer.normalize(sentence, context.normalization),
                    semantics=semantics,
                    check_patterns=check_patterns,
                    validator_enforcement_shape=validator_shape,
                    update_patterns=_infer_update_patterns(sentence, validator_shape),
                    state_fields=_infer_state_fields(sentence, validator_shape),
                    status=_status_for_patterns(kind, check_patterns),
                )
            )
        return contracts


class JsonContractExtractor:
    """LLM-facing extractor with strict JSON validation and no heuristic repair."""

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
                return []
            payload = json.loads(raw[start : end + 1])

        if isinstance(payload, dict):
            payload = [payload]
        contracts: list[Contract] = []
        for item in payload:
            try:
                contracts.append(Contract.model_validate(item))
            except ValidationError:
                continue
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
            max_retries=0,
            timeout=self.config.llm_timeout_seconds,
        )
        self._sleep = time.sleep

    @classmethod
    def from_env(
        cls,
        env_file: str | Path | None = None,
        *,
        system_prompt: str = CONTRACT_EXTRACTION_SYSTEM_PROMPT,
    ) -> "OpenAIChatResponseProvider":
        return cls(load_config(env_file), system_prompt=system_prompt)

    def __call__(self, prompt: str, *, system_prompt: str | None = None) -> str:
        for attempt in range(1, LLM_MAX_ATTEMPTS + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.llm_model or "",
                    temperature=0,
                    max_tokens=self.config.llm_max_tokens,
                    messages=[
                        {
                            "role": "system",
                            "content": system_prompt or self.system_prompt,
                        },
                        {"role": "user", "content": prompt},
                    ],
                )
                return response.choices[0].message.content or ""
            except (APITimeoutError, TimeoutError) as exc:
                log_event(
                    LOGGER,
                    "llm.timeout",
                    attempt=attempt,
                    max_attempts=LLM_MAX_ATTEMPTS,
                )
                if attempt == LLM_MAX_ATTEMPTS:
                    raise LLMCallError.timeout(attempts=attempt) from exc
                self._sleep(0.25 * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")


class CandidateJsonContractExtractor:
    """LLM-first extractor; local code only validates schema-shaped fields."""

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
            prompt=_user_turn_candidate_prompt(text, context),
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
            contract_text = str(item.get("text") or "").strip()
            if not contract_text:
                continue
            raw_effect = item.get("effect")
            effect = _enum_value(RuleEffect, raw_effect, RuleEffect.PREFER)
            default_kind = _kind_from_effect(effect)
            kind = _enum_value(
                ContractKind,
                item.get("kind"),
                default_kind,
            )
            modality = _enum_value(Modality, item.get("modality"), _default_modality(kind))
            strength = _enum_value(Strength, item.get("strength"), _default_strength(kind))
            semantics_payload = item.get("semantics") or {}
            semantic_actions = _string_list(
                semantics_payload.get("actions") if isinstance(semantics_payload, dict) else None
            )
            semantic_tags = _string_list(
                semantics_payload.get("tags") if isinstance(semantics_payload, dict) else None
            )
            scope = _parse_scope(item.get("scope"), context)
            validator_shape = _parse_validator_shape(
                item.get("validator_enforcement_shape") or item.get("enforcement_shape")
            )
            if validator_shape is None:
                continue
            check_patterns = _parse_tool_patterns(item.get("check_patterns"))
            update_patterns = _parse_tool_patterns(item.get("update_patterns"))
            state_fields = _string_list(item.get("state_fields"))
            if effect == RuleEffect.PREFER or kind == ContractKind.PREFERENCE or strength == Strength.SOFT:
                continue
            if validator_shape == ValidatorEnforcementShape.CHECK_ONLY:
                update_patterns = []
                state_fields = []
            validity = _parse_validity(item, context)
            lifecycle = _lifecycle_from_validity(validity)
            source = ContractSource(
                kind=source_kind,
                conversation_id=context.conversation_id,
                turn_id=context.turn_id,
                path=path,
                fingerprint=fingerprint,
                metadata=_source_metadata(context) if source_kind == SourceKind.USER_TURN else {},
                created_at=context.normalization.current_time(),
            )
            contracts.append(
                Contract(
                    text=contract_text,
                    effect=effect,
                    kind=kind,
                    modality=modality,
                    strength=strength,
                    source=source,
                    scope=scope,
                    lifecycle=lifecycle,
                    validity=validity,
                    semantics=RuleSemantics(actions=semantic_actions, tags=semantic_tags),
                    validator_enforcement_shape=validator_shape,
                    check_patterns=check_patterns,
                    update_patterns=update_patterns,
                    state_fields=state_fields,
                    status=ContractStatus.ACTIVE,
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
        return ContractKind.PROCEDURE, Modality.MUST, Strength.HARD
    return ContractKind.REQUIREMENT, Modality.MUST, Strength.HARD


def _infer_semantics(text: str) -> RuleSemantics:
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
    if any(token in lower for token in ("budget", "cost", "purchase", "checkout", "booking", "spend")):
        host_actions.add("purchase")
        tags.update({"spend", "budget"})
    if any(token in lower for token in ("test", "tests", "pytest")):
        host_actions.add("exec")
        tags.add("test")
    if any(token in lower for token in ("email", "message", "messages", "slack", "send", "notify")):
        host_actions.update({"email.send", "message.send"})
        tags.update({"external_write", "notify_human"})
    if "memory" in lower:
        host_actions.add("memory.write")
        tags.add("memory_write")
    if any(
        token in lower
        for token in ("report", "reporting", "summary", "summaries", "explain", "answer")
    ):
        host_actions.add("agent.response")
        tags.update({"prompt_intake", "response_style"})
    return RuleSemantics(actions=sorted(host_actions), tags=sorted(tags))


def _status_for_patterns(kind: ContractKind, check_patterns: list[ToolPattern]) -> ContractStatus:
    if kind == ContractKind.PROHIBITION and not check_patterns:
        return ContractStatus.CANDIDATE
    return ContractStatus.ACTIVE


def _parse_validator_shape(value) -> ValidatorEnforcementShape | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("-", "_")
    try:
        return ValidatorEnforcementShape(normalized)
    except ValueError:
        return None


def _infer_validator_enforcement_shape(text: str) -> ValidatorEnforcementShape:
    lower = text.lower()
    if _looks_like_budget_rule(lower):
        return ValidatorEnforcementShape.CHECK_UPDATE
    return ValidatorEnforcementShape.CHECK_ONLY


def _reconcile_validator_enforcement_shape(
    text: str,
    proposed: ValidatorEnforcementShape | None,
) -> ValidatorEnforcementShape:
    inferred = _infer_validator_enforcement_shape(text)
    if proposed is None:
        return inferred
    if proposed == ValidatorEnforcementShape.CHECK_UPDATE:
        return proposed
    if proposed == ValidatorEnforcementShape.CHECK_ONLY:
        return proposed if _depends_on_prior_action_or_user_response(text.lower()) else inferred
    return inferred


def _depends_on_prior_action_or_user_response(lower: str) -> bool:
    history_cues = (
        "before ",
        "after ",
        "prior ",
        "previous ",
        "already ",
        "until ",
        "per day",
        "per week",
        "ask me",
        "asking me",
        "approve",
        "approval",
        "confirm",
        "explicitly say",
    )
    return any(cue in lower for cue in history_cues)


def _infer_check_patterns(
    text: str,
    shape: ValidatorEnforcementShape,
) -> list[ToolPattern]:
    lower = text.lower()
    if _looks_like_budget_rule(lower):
        return _purchase_tool_patterns()
    if "push" in lower:
        return _command_tool_patterns(r"^git\s+push(\s|$)")
    return _infer_tool_patterns(text, [])


def _infer_update_patterns(
    text: str,
    shape: ValidatorEnforcementShape,
) -> list[ToolPattern]:
    if shape != ValidatorEnforcementShape.CHECK_UPDATE:
        return []
    if _looks_like_budget_rule(text.lower()):
        return _purchase_tool_patterns()
    return []


def _infer_state_fields(text: str, shape: ValidatorEnforcementShape) -> list[str]:
    if shape != ValidatorEnforcementShape.CHECK_UPDATE:
        return []
    if _looks_like_budget_rule(text.lower()):
        return [
            "spent_cents",
            "seen_entry_seqs",
            "unknown_spend_entry_seqs",
            "last_seen_seq",
        ]
    return []


def _looks_like_budget_rule(lower: str) -> bool:
    return any(token in lower for token in ("budget", "total cost", "cost", "spend")) and any(
        token in lower for token in ("exceed", "under", "less than", "not exceed", "$")
    )


def _parse_tool_patterns(value) -> list[ToolPattern]:
    if not isinstance(value, list):
        return []
    patterns: list[ToolPattern] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            patterns.append(ToolPattern.model_validate(item))
        except ValidationError:
            continue
    return patterns


def _parse_scope(
    value: object,
    context: ExtractionContext,
) -> Scope:
    fallback = _default_scope(context)
    if not isinstance(value, dict):
        return fallback
    level = str(value.get("level") or "").strip().lower()
    if level not in {item.value for item in ScopeLevel}:
        return fallback
    workspace = (
        _clean_string(value.get("workspace"))
        or context.normalization.workspace
        or context.normalization.repo
    )
    project = _clean_string(value.get("project")) or context.normalization.repo or workspace
    module = str(value.get("module") or "").strip() or None
    path = _clean_string(value.get("path") or value.get("folder") or value.get("file"))
    try:
        if level == ScopeLevel.GLOBAL.value:
            return Scope(level=ScopeLevel.GLOBAL, user_id=context.normalization.user_id)
        if level == ScopeLevel.SESSION.value:
            return Scope(
                level=ScopeLevel.SESSION,
                workspace=context.normalization.workspace,
                user_id=context.normalization.user_id,
            )
        if level == ScopeLevel.WORKSPACE.value:
            return Scope(
                level=ScopeLevel.WORKSPACE,
                workspace=workspace,
                user_id=context.normalization.user_id,
            )
        if level == ScopeLevel.PATH.value:
            return Scope(
                level=ScopeLevel.PATH,
                workspace=workspace,
                path=path,
                user_id=context.normalization.user_id,
            )
        if level == ScopeLevel.PROJECT.value:
            return Scope(
                level=ScopeLevel.WORKSPACE if workspace and not project else ScopeLevel.PROJECT,
                workspace=workspace or project,
                project=project,
                user_id=context.normalization.user_id,
            )
        if level == ScopeLevel.MODULE.value:
            return Scope(
                level=ScopeLevel.MODULE,
                workspace=context.normalization.workspace or project,
                project=project,
                module=module,
                user_id=context.normalization.user_id,
            )
    except ValueError:
        return fallback
    return fallback


def _default_scope(context: ExtractionContext) -> Scope:
    workspace = context.normalization.workspace or context.normalization.repo
    if workspace:
        return Scope(
            level=ScopeLevel.WORKSPACE,
            workspace=workspace,
            user_id=context.normalization.user_id,
        )
    return Scope(level=ScopeLevel.GLOBAL, user_id=context.normalization.user_id)


def _clean_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_validity(item: dict, context: ExtractionContext) -> RuleValidity:
    validity_payload = item.get("validity")
    valid_until = (
        item.get("valid_until")
        if "valid_until" in item
        else item.get("validate_until")
    )
    if isinstance(validity_payload, dict):
        valid_until = validity_payload.get("until", valid_until)
    payload = {
        "from": context.normalization.current_time(),
        "until": valid_until,
    }
    try:
        return RuleValidity.model_validate(payload)
    except ValidationError:
        return RuleValidity(start=context.normalization.current_time())


def _lifecycle_from_validity(validity: RuleValidity) -> Lifecycle:
    if validity.until is None:
        return Lifecycle(
            type=LifecycleType.UNTIL_REVOKED,
            effective_from=validity.start,
            until_revoked=True,
            original_text="valid_until=null",
        )
    return Lifecycle(
        type=LifecycleType.BOUNDED_TIME,
        effective_from=validity.start,
        expires_at=validity.until,
        original_text=f"valid_until={validity.until.isoformat()}",
    )


def _infer_tool_patterns(text: str, path_globs: list[str]) -> list[ToolPattern]:
    semantics = _infer_semantics(text)
    patterns: list[ToolPattern] = []
    actions = set(semantics.actions)
    if "git.push" in actions:
        patterns.extend(_command_tool_patterns(r"^git\s+push(\s|$)"))
    if "git.commit" in actions:
        patterns.extend(_command_tool_patterns(r"^git\s+commit(\s|$)"))
    if "dependency.install" in actions:
        patterns.extend(_command_tool_patterns(r"^(?:npm|pnpm|yarn|uv|pip|pipx)\s+(?:install|add|sync)(\s|$)"))
    if "purchase" in actions:
        patterns.extend(_purchase_tool_patterns())
    if {"file.write", "file.delete"}.intersection(actions):
        patterns.extend(_file_tool_patterns(path_globs))
    if "web.search" in actions:
        patterns.extend(
            [
                ToolPattern(tool="WebSearch"),
                ToolPattern(tool="web_search"),
                ToolPattern(tool="web.search"),
                ToolPattern(tool="search"),
            ]
        )
    if "message.send" in actions:
        patterns.extend(
            [
                ToolPattern(tool="message.send"),
                ToolPattern(tool="send_message"),
                ToolPattern(tool="message"),
                ToolPattern(tool="sessions_send"),
            ]
        )
    if "email.send" in actions:
        patterns.extend([ToolPattern(tool="email.send"), ToolPattern(tool="send_email")])
    if "memory.write" in actions:
        patterns.extend([ToolPattern(tool="memory.write"), ToolPattern(tool="memory_record")])
    if "agent.response" in actions:
        patterns.append(ToolPattern(tool="agent.response"))
    return _dedupe_tool_patterns(patterns)


def _purchase_tool_patterns() -> list[ToolPattern]:
    return [
        ToolPattern(tool="purchase"),
        ToolPattern(tool="checkout"),
        ToolPattern(tool="booking"),
    ]


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


_EXTRACTION_TASK_LINE = (
    "Extract hard runtime contracts that agent must enforce with validation hooks in later actions from the source text."
)


def _user_turn_candidate_prompt(text: str, context: ExtractionContext | None = None) -> str:
    """Build the user message: tool capsules first (KV-cache stable), then the source text.

    All extraction requirements live in CONTRACT_EXTRACTION_SYSTEM_PROMPT. The user message
    only carries the per-agent tool capsules, any similar-rule context, and the source text.
    """
    sections: list[str] = []
    if context is not None and context.tool_capsule_system_prompt:
        sections.append(context.tool_capsule_system_prompt)
    sections.append(_EXTRACTION_TASK_LINE)
    if context is not None:
        sections.append(
            "Extraction context:\n"
            f"- current_time: {context.normalization.current_time().isoformat()}\n"
            f"- default_workspace: {context.normalization.workspace or context.normalization.repo or ''}\n"
            f"- session_id: {context.session_id or ''}"
        )
    if context is not None and context.similar_rules_system_prompt:
        sections.append(context.similar_rules_system_prompt)
    sections.append(f"Source text:\n{text}")
    return "\n\n".join(sections)


def _cold_start_candidate_prompt(text: str, source_kind: SourceKind) -> str:
    del source_kind
    return f"{_EXTRACTION_TASK_LINE}\n\nSource text:\n{text}"


def _system_prompt_for_context(context: ExtractionContext) -> str:
    del context
    return CONTRACT_EXTRACTION_SYSTEM_PROMPT


def _source_metadata(context: ExtractionContext) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if context.session_id:
        metadata["session_id"] = context.session_id
    return metadata


def _call_response_provider(
    response_provider: Callable[[str], str],
    *,
    prompt: str,
    system_prompt: str,
) -> str:
    if _accepts_system_prompt(response_provider):
        return response_provider(prompt, system_prompt=system_prompt)  # type: ignore[call-arg]
    return response_provider(f"{system_prompt}\n\n{prompt}")


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


def _default_strength(kind: ContractKind) -> Strength:
    if kind == ContractKind.PREFERENCE:
        return Strength.SOFT
    return Strength.HARD


def _kind_from_effect(effect: RuleEffect) -> ContractKind:
    if effect == RuleEffect.DENY:
        return ContractKind.PROHIBITION
    if effect == RuleEffect.ALLOW:
        return ContractKind.EXCEPTION
    if effect == RuleEffect.REQUIRE:
        return ContractKind.REQUIREMENT
    return ContractKind.PREFERENCE


def _effect_from_kind(kind: ContractKind) -> RuleEffect:
    if kind == ContractKind.PROHIBITION:
        return RuleEffect.DENY
    if kind == ContractKind.EXCEPTION:
        return RuleEffect.ALLOW
    if kind in {ContractKind.REQUIREMENT, ContractKind.PROCEDURE}:
        return RuleEffect.REQUIRE
    return RuleEffect.PREFER


def _string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


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
