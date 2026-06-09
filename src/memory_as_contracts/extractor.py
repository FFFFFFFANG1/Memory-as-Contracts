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
    Modality,
    RuleEffect,
    RuleSemantics,
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

Before returning, produce the final internally consistent contract set for this
source only. Merge duplicate restatements. When the source gives incompatible
instructions for the same scope and semantic action, treat the later explicit
instruction as the final version and do not emit the superseded version. A
concrete narrower allowance is an exception, not an unresolved conflict, so emit
both the broader rule and the narrower exception. Do not compare against stored
similar rules; cross-source and historical relations are handled after extraction.
Return only valid JSON, no markdown.
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
            scope = self.scope_normalizer.normalize(sentence, context.normalization)
            semantics = _infer_semantics(sentence)
            tool_patterns = _infer_tool_patterns(sentence, scope.path_globs)
            validator_shape = _infer_validator_enforcement_shape(sentence)
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
                    tool_patterns=tool_patterns,
                    validator_enforcement_shape=validator_shape,
                    check_patterns=_infer_check_patterns(sentence, validator_shape),
                    update_patterns=_infer_update_patterns(sentence, validator_shape),
                    state_fields=_infer_state_fields(sentence, validator_shape),
                    status=_status_for_patterns(kind, tool_patterns),
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
            raw_effect = item.get("effect")
            default_kind = _kind_from_effect(_enum_value(RuleEffect, raw_effect, RuleEffect.PREFER))
            kind = _enum_value(
                ContractKind,
                item.get("kind"),
                default_kind,
            )
            effect = _enum_value(RuleEffect, raw_effect, _effect_from_kind(kind))
            if kind == ContractKind.EXCEPTION and _is_meta_exception(contract_text):
                continue
            modality = _enum_value(Modality, item.get("modality"), _default_modality(kind))
            strength = _enum_value(Strength, item.get("strength"), Strength.SOFT)
            inferred_semantics = _infer_semantics(contract_text)
            semantics_payload = item.get("semantics") or {}
            semantic_actions = sorted(
                {
                    *_string_list(semantics_payload.get("actions") if isinstance(semantics_payload, dict) else None),
                    *inferred_semantics.actions,
                }
            )
            semantic_tags = sorted(
                {
                    *_string_list(semantics_payload.get("tags") if isinstance(semantics_payload, dict) else None),
                    *inferred_semantics.tags,
                }
            )
            scope = self.scope_normalizer.normalize(contract_text, context.normalization)
            tool_patterns = _parse_tool_patterns(item.get("tool_patterns"))
            if not tool_patterns:
                tool_patterns = _infer_tool_patterns(contract_text, scope.path_globs)
            proposed_validator_shape = _parse_validator_shape(
                item.get("validator_enforcement_shape") or item.get("enforcement_shape")
            )
            validator_shape = _reconcile_validator_enforcement_shape(
                contract_text,
                proposed_validator_shape,
            )
            check_patterns = _parse_tool_patterns(item.get("check_patterns"))
            update_patterns = _parse_tool_patterns(item.get("update_patterns"))
            if validator_shape != ValidatorEnforcementShape.NO_VALIDATOR and not check_patterns:
                check_patterns = _infer_check_patterns(contract_text, validator_shape)
            if validator_shape == ValidatorEnforcementShape.CHECK_UPDATE and not update_patterns:
                update_patterns = _infer_update_patterns(contract_text, validator_shape)
            state_fields = _string_list(item.get("state_fields")) or _infer_state_fields(
                contract_text,
                validator_shape,
            )
            if validator_shape == ValidatorEnforcementShape.NO_VALIDATOR:
                check_patterns = []
                update_patterns = []
                state_fields = []
            elif validator_shape == ValidatorEnforcementShape.CHECK_ONLY:
                update_patterns = []
                state_fields = []
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
                    effect=effect,
                    kind=kind,
                    modality=modality,
                    strength=strength,
                    source=source,
                    scope=scope,
                    lifecycle=self.lifecycle_normalizer.normalize(
                        contract_text, context.normalization
                    ),
                    semantics=RuleSemantics(actions=semantic_actions, tags=semantic_tags),
                    tool_patterns=tool_patterns,
                    validator_enforcement_shape=validator_shape,
                    check_patterns=check_patterns,
                    update_patterns=update_patterns,
                    state_fields=state_fields,
                    status=_status_for_patterns(kind, tool_patterns),
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


def _status_for_patterns(kind: ContractKind, tool_patterns: list[ToolPattern]) -> ContractStatus:
    if kind == ContractKind.PROHIBITION and not tool_patterns:
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
    if _depends_on_prior_action_or_user_response(lower):
        return ValidatorEnforcementShape.CHECK_ONLY
    return ValidatorEnforcementShape.NO_VALIDATOR


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
    if shape == ValidatorEnforcementShape.NO_VALIDATOR:
        return []
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
- effect: one of deny, allow, require, prefer
- semantics.actions: compact semantic action labels for retrieval, dedup, and relation analysis
- semantics.tags: compact semantic tags for retrieval, dedup, and relation analysis
- tool_patterns: required non-empty deterministic operational patterns using native tool names and raw argument names from the provided tool capsules. Each item is {{"tool":"NativeToolName","args":{{"arg_name":{{"regex":"...", "path_glob":"...", "mentions_path_glob":"..."}}}}}}.
- validator_enforcement_shape: one of no_validator, check_only, check_update
- check_patterns: native tool patterns for pending actions that require validator check
- update_patterns: native tool patterns for committed actions that update materialized state
- state_fields: state keys maintained by check_update validators

Rules:
- Source kind is {source_kind.value}. {source_instruction}
- Add durable user-turn contracts only when the text is repeated across turns/sources or clearly scopes beyond the current turn, such as task, session, project, repo, file/path, component/module, organization, or global scope.
- Semantics is only the behavioral summary used for retrieval and relation checks. It does not replace tool_patterns.
- For non-gated preferences or procedures about planning, explanations, reports, summaries, or final answers, use the reserved MAC prompt-intake surface {{"tool":"agent.response"}}. `agent.response` is the only valid pattern surface that does not need to appear in host tool capsules. Do not omit a durable response/planning preference merely because it has no host tool, and do not use agent.response for deny/allow hook enforcement.
- Every returned contract must include at least one valid tool_patterns entry. If a deny/allow/require rule cannot be grounded to a native tool pattern from the available tool capsules, omit that item from this extraction response.
- Extractor proposes patterns and enforcement shape only; it never writes Python.
- Use check_only when enforcement needs only the Pending Action plus a bounded Action Log search.
- Use check_update only when enforcement needs an incrementally maintained numeric or symbolic state. A simple prior-action query such as "run tests before push" must not use update_patterns.
- For no_validator, return empty check_patterns, update_patterns, and state_fields.
- For check_only, return non-empty check_patterns and empty update_patterns/state_fields.
- For check_update, return non-empty check_patterns/update_patterns and explicit state_fields.
- Tool names and argument fields in all patterns must come from the provided adapter tool capsules.
- Temporary/narrow allowance that overrides a broader rule must use effect "allow", but only when the source names a concrete allowed action and concrete scope. Do not extract meta exception language such as "unless a narrower exception says so" as its own exception.
- Non-obvious workflow preferences still count if they constrain future behavior.
- Represent every explicit durable rule in the source that can be grounded to a valid tool pattern. For bullet lists, inspect every bullet independently before returning.
- Return the final internally consistent contract set for this source. Merge duplicate restatements that impose the same behavior and scope, keeping the clearest and most complete version.
- When this source contains incompatible instructions for the same scope and semantic action, treat the later explicit instruction as the final version and emit only the final effective version. Do not keep the superseded local version.
- A concrete narrower allowance is an exception rather than an unresolved conflict. Emit both the broader rule and the narrower exception so the Conflict Resolver can create the scoped edge.
- Do not compare against stored similar rules. They are intentionally absent from this extractor prompt; cross-source and historical deduplication/conflict resolution happens after extraction.
- Before returning, perform a source-coverage check: every explicit durable prohibition, requirement, concrete exception, and future-facing preference must either appear in the contracts array or be intentionally omitted because it cannot be grounded to an available tool surface.
- For hook matching, tool is exact native tool name. Parameter constraints match raw tool argument strings.
    Example: for Claude Code Bash git push, use {{"tool":"Bash","args":{{"command":{{"regex":"^git\\\\s+push(\\\\s|$)"}}}}}}.

Return JSON shape:
{{"contracts": [{{"text": "Do not run git push until I approve it.", "source_span": "do not run git push until I approve it", "effect": "deny", "semantics": {{"actions": ["git.push"], "tags": ["publish_code", "external_write"]}}, "tool_patterns": [{{"tool": "Bash", "args": {{"command": {{"regex": "^git\\\\s+push(\\\\s|$)"}}}}}}], "validator_enforcement_shape": "check_only", "check_patterns": [{{"tool": "Bash", "args": {{"command": {{"regex": "^git\\\\s+push(\\\\s|$)"}}}}}}], "update_patterns": [], "state_fields": []}}]}}

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
