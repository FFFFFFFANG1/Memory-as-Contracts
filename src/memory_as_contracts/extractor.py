from __future__ import annotations

import json
import inspect
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

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
from memory_as_contracts.policy_ir import PolicyIR


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
                    **_chat_completion_extra_kwargs(self.config),
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


POLICY_IR_EXTRACTION_SYSTEM_PROMPT = """
You compile user-stated hard runtime constraints for an AI agent into compact
PolicyIR JSON. Return only valid JSON.

A runtime constraint is a durable rule that changes future agent behavior and is
observable at runtime. Extract a policy only when the text has:
- normative force: must, must not, may only, may be used at most, before/after,
  whenever, every response/tool call, or equivalent mandatory wording;
- governed behavior: a tool call, tool/action count, action sequence, required
  evidence source, or final send_message response;
- observable verifier: pending tool call args, committed action_log, or final
  response text.

Recognize hard contracts:
- prohibition: forbids an action or class of actions.
- requirement: requires an action, check, condition, format, or evidence source.
- procedure: specifies a mandatory workflow, tool, command, or process.
- exception: gives a concrete narrower allowance in a bounded scope.

Durability filter: extract only constraints meant to apply beyond the current
one-off request. Durability can come from explicit scope (global, session,
workspace, path/project/phase), repeated use, or standing-rule language. Do not
extract soft preferences, personal taste, ordinary task content, background
facts, one-off instructions for only the current answer/tool call, meta
statements about possible future exceptions, or duplicate paraphrases of a rule
already captured in the same scope.

Scope and context are not obligations. Project/phase/background statements only
choose where a rule applies. If a sentence only says what project/phase/task is
active, output no policy.

Current task objectives are not memory constraints. If the user is just asking
the agent to find/confirm/retrieve something now, output no policy.

Evidence-source rules are constraints when they govern the final answer, e.g.
the answer/information/facts must come from tool calls rather than memory; encode
them as required_tool_usage targeting response/message.send.

If compliance requires hidden reasoning, private scratchpad, unlogged working
notes, subjective judgment, or future retry intent not visible in pending
action/action_log/response, use unsupported_reason rather than inventing a
monitor.

Before-tool rules are executable only when the required prior event is itself
observable in action_log, such as a specific earlier tool call. If the required
prior event is an outline, roadmap, checklist, candidate list, working note, or
other preparatory text that is not captured as a tool/action_log entry before
the pending tool call, mark it unsupported.

Effect semantics: use require for mandatory formats, evidence requirements,
sequences, counts, and upper/lower bounds; use deny only for explicitly
forbidden behavior/content; use allow only for explicit exceptions to another
rule.

Boundary examples:
- Observable: "Before answering, use search_tool at least once." This can be
  checked in action_log, so emit required_tool_usage targeting response.
- Not observable: "Before using tools, write a private plan/notes first." The
  private text is not in action_log or final response before the tool call, so
  emit unsupported_reason or no policy.
- Observable prior action: "Before tool B, call tool A." Target only tool B;
  monitor only prior tool A in action_log. Do not put both A and B in target.
- Separate gated_action from satisfying_action. The target is the action that
  may be blocked; the monitor is the prior action that can satisfy the rule.
  Never target the satisfying tool itself for "before X, do Y" constraints.
- If the gated action is vague, generic, or only says "before using tools",
  bind the policy to response/message.send unless the text names a concrete
  tool/action that should be blocked.

Allowed output shape:
{"policies":[
  {
    "text":"concise source constraint",
    "effect":"deny|allow|require",
    "scope":{"level":"global|workspace|session|path","path":"optional/path"},
    "valid_until":null,
    "target":{
      "phase":"pre|post|response",
      "tool":"optional exact tool name",
      "tools":["optional exact tool names"],
      "action_family":"optional action family such as message.send, cctu.tool.execute, tool.call",
      "action_families":["optional action families"]
    },
    "obligation":{
      "kind":"current_action|response|action_count|specific_tool_count|tool_count|prior_action|required_tool_usage|interaction_turn_count|sequence|same_step",
      "predicate":{"field":"response","op":"regex|not_regex|contains|not_contains|json_object|word_count_lte|word_count_gte|word_count_between|char_count_lte|char_count_gte|char_count_between|endswith|startswith","value":"..."},
      "monitor":{"source":"action_log","where":{"field":"tool_name|action_family","op":"eq|in|regex","value":"..."},"aggregate":"count|exists|distinct_count","distinct_by":"tool_name","group_by":"turn_id"},
      "op":"lte|gte|eq|between",
      "value":1
    },
    "unsupported_reason":null
  }
]}

Important:
- Do not output ids, source metadata, status, relation labels, priorities, or
  canonical keys. The local system creates those.
- Use exact tool names only when they appear in the provided tool capsules or
  source text.
- Output atomic policies: split compound instructions into one policy per
  response format/content/length rule, one policy per tool-count limit, and one
  policy per required prior tool/evidence rule.
- Bind final answer formatting/content constraints to target phase "response"
  and action_family "message.send".
- Bind tool count or forbidden-tool constraints to target phase "pre" and the
  relevant tool or action_family "tool.call".
- Bind cross-check, verification, evidence, reporting, or recording constraints
  to response/message.send unless the text explicitly forbids or limits a
  pending tool call.
- For prior_action, the target is the later action being gated; the monitor is
  the earlier observable action that must already exist in action_log. If the
  later action is answering, reporting, recording, or finalizing, target
  response/message.send.
- Do not encode retry-on-failure instructions as pre-tool constraints unless
  the verifier can observe both the failed action and a corrected retry in
  action_log. Otherwise use unsupported_reason.
- Use current_action only for constraints with a concrete predicate over the
  pending tool call or its arguments. Do not use current_action for context
  declarations such as "we are now in phase X".
- For "tool X at most N times", use kind "specific_tool_count", target tool X,
  monitor where tool_name == X, op "lte", value N.
- For "never call tool X", use kind "specific_tool_count", target tool X,
  monitor where tool_name == X, op "lte", value 0.
- For "at most N total tool calls", use kind "tool_count", target action_family
  "tool.call", monitor where action_family == "tool.call", op "lte", value N.
- For "between A and B interaction turns/calls", output two policies: one with
  op "gte" value A and one with op "lte" value B.
- For response length ranges, prefer one response predicate:
  char_count_between or word_count_between with value [min,max].
- For same-step/parallel tool requirements, use kind "same_step", target
  response/message.send, monitor where tool_name in [tools], aggregate
  distinct_count, distinct_by "tool_name", group_by "turn_id", value equal to
  the number of required distinct tools.
- If same-step requires multiple calls to the same tool with different
  arguments, use aggregate "count", group_by "turn_id", and value equal to the
  required number of calls.
- For interaction_turn_count, target response/message.send and count both tool
  calls and the pending final response with monitor action_family in
  ["tool.call","message.send"].
- For "must use/cross-check with tool X before answering", bind target phase
  "response", kind "required_tool_usage", monitor where tool_name == X, value 1.
- If several hard constraints appear in one sentence, split them into multiple
  policies when they have different targets or obligations.
""".strip()


class PolicyIRContractExtractor:
    """LLM extractor that stores semantic PolicyIR instead of generated code hooks."""

    def __init__(
        self,
        response_provider: Callable[[str], str],
        *,
        system_prompt: str = POLICY_IR_EXTRACTION_SYSTEM_PROMPT,
    ) -> None:
        self.response_provider = response_provider
        self.system_prompt = system_prompt
        self._diagnostics: list[dict[str, Any]] = []
        self._diagnostics_lock = Lock()

    def drain_diagnostics(self) -> list[dict[str, Any]]:
        with self._diagnostics_lock:
            diagnostics = list(self._diagnostics)
            self._diagnostics.clear()
        return diagnostics

    def _record_diagnostic(self, diagnostic: dict[str, Any]) -> None:
        with self._diagnostics_lock:
            self._diagnostics.append(diagnostic)

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
        prompt = _policy_ir_user_prompt(text, context)
        raw = _call_response_provider(
            self.response_provider,
            prompt=prompt,
            system_prompt=self.system_prompt,
        )
        contracts, diagnostic = _parse_policy_ir_contracts_with_diagnostics(raw, context=context)
        diagnostic["source"] = "online_user_turn"
        self._record_diagnostic(diagnostic)
        return contracts

    def extract_cold_start_source(
        self,
        *,
        text: str,
        source_kind: SourceKind,
        context: ExtractionContext,
        path: str | None = None,
        fingerprint: str | None = None,
    ) -> list[Contract]:
        prompt = _policy_ir_user_prompt(text, context)
        raw = _call_response_provider(
            self.response_provider,
            prompt=prompt,
            system_prompt=self.system_prompt,
        )
        contracts, diagnostic = _parse_policy_ir_contracts_with_diagnostics(
            raw,
            context=context,
            source_kind=source_kind,
            path=path,
            fingerprint=fingerprint,
        )
        diagnostic["source"] = "cold_start"
        self._record_diagnostic(diagnostic)
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


def _chat_completion_extra_kwargs(config: MacConfig) -> dict[str, Any]:
    if not _disable_thinking_for_endpoint(config):
        return {}
    return {"extra_body": {"thinking": {"type": "disabled"}}}


def _disable_thinking_for_endpoint(config: MacConfig) -> bool:
    override = os.getenv("MAC_LLM_DISABLE_THINKING")
    if override is not None:
        return override.strip().lower() not in {"0", "false", "no", "off"}
    base_url = (config.openai_base_url or "").lower()
    return "ark.cn-" in base_url and "/coding/" in base_url


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


def _policy_ir_user_prompt(text: str, context: ExtractionContext) -> str:
    sections: list[str] = []
    if context.tool_capsule_system_prompt:
        sections.append(_compact_tool_capsule_prompt(context.tool_capsule_system_prompt))
    sections.append(
        "Extraction context:\n"
        f"- current_time: {context.normalization.current_time().isoformat()}\n"
        f"- default_workspace: {context.normalization.workspace or context.normalization.repo or ''}\n"
        f"- session_scope: {context.session_id or ''}\n"
        "Only output semantic PolicyIR fields. Do not output ids/status/source metadata."
    )
    if context.similar_rules_system_prompt:
        sections.append(context.similar_rules_system_prompt)
    sections.append(f"Source text:\n{text}")
    return "\n\n".join(sections)


def _compact_tool_capsule_prompt(raw: str) -> str:
    try:
        start = raw.find("{")
        payload = json.loads(raw[start:]) if start >= 0 else {}
    except (json.JSONDecodeError, TypeError):
        return raw[:4000]
    tools = []
    for item in payload.get("tools", []):
        if not isinstance(item, dict):
            continue
        schema = item.get("input_schema") if isinstance(item.get("input_schema"), dict) else {}
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        tools.append(
            {
                "name": item.get("name"),
                "description": str(item.get("description") or "")[:180],
                "args": sorted(str(key) for key in props),
            }
        )
    return "Tool capsules:\n" + json.dumps({"tools": tools}, ensure_ascii=False, sort_keys=True)


def _parse_policy_ir_contracts(
    raw: str,
    *,
    context: ExtractionContext,
    source_kind: SourceKind = SourceKind.USER_TURN,
    path: str | None = None,
    fingerprint: str | None = None,
) -> list[Contract]:
    contracts, _diagnostic = _parse_policy_ir_contracts_with_diagnostics(
        raw,
        context=context,
        source_kind=source_kind,
        path=path,
        fingerprint=fingerprint,
    )
    return contracts


def _parse_policy_ir_contracts_with_diagnostics(
    raw: str,
    *,
    context: ExtractionContext,
    source_kind: SourceKind = SourceKind.USER_TURN,
    path: str | None = None,
    fingerprint: str | None = None,
) -> tuple[list[Contract], dict[str, Any]]:
    diagnostic: dict[str, Any] = {
        "raw_chars": len(raw),
        "json_loaded": False,
        "policy_items": 0,
        "extracted_count": 0,
        "missing_text_count": 0,
        "unsupported_count": 0,
        "validation_error_count": 0,
        "validation_errors": [],
        "zero_policy": False,
    }
    payload, load_error = _load_policy_payload_with_error(raw)
    if load_error:
        diagnostic["json_error"] = load_error
        diagnostic["zero_policy"] = True
        return [], diagnostic
    diagnostic["json_loaded"] = True
    policies = payload.get("policies", payload.get("contracts", []))
    if not isinstance(policies, list):
        diagnostic["json_error"] = "policies_not_list"
        diagnostic["zero_policy"] = True
        return [], diagnostic
    diagnostic["policy_items"] = len(policies)
    contracts: list[Contract] = []
    for item in policies:
        if not isinstance(item, dict):
            diagnostic["validation_error_count"] += 1
            continue
        text = _clean_string(item.get("text"))
        if not text:
            diagnostic["missing_text_count"] += 1
            continue
        if _clean_string(item.get("unsupported_reason")):
            diagnostic["unsupported_count"] += 1
            continue
        policy_payload = _normalize_policy_payload(item, text=text, context=context)
        try:
            policy = PolicyIR.model_validate(policy_payload)
        except ValidationError as exc:
            diagnostic["validation_error_count"] += 1
            errors = diagnostic["validation_errors"]
            if isinstance(errors, list) and len(errors) < 3:
                errors.append(
                    {
                        "text": text[:160],
                        "error": "; ".join(
                            f"{'.'.join(str(part) for part in err.get('loc', ()))}:{err.get('msg')}"
                            for err in exc.errors()[:3]
                        ),
                    }
                )
            continue
        if _is_non_executable_policy(policy):
            diagnostic["unsupported_count"] += 1
            continue
        effect = _enum_value(RuleEffect, policy.effect, RuleEffect.REQUIRE)
        kind = _kind_from_effect(effect)
        scope = _parse_ir_scope(policy.scope, context)
        validity = _parse_validity(
            {"valid_until": policy.valid_until},
            context,
        )
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
                text=text,
                effect=effect,
                kind=kind,
                modality=_default_modality(kind),
                strength=Strength.HARD,
                source=source,
                scope=scope,
                lifecycle=_lifecycle_from_validity(validity),
                validity=validity,
                semantics=_semantics_from_policy(policy),
                policy_ir=policy.model_dump(mode="json", by_alias=True, exclude_none=True),
                status=ContractStatus.ACTIVE,
            )
        )
    diagnostic["extracted_count"] = len(contracts)
    diagnostic["zero_policy"] = len(contracts) == 0
    return contracts, diagnostic


def _load_policy_payload(raw: str) -> dict:
    payload, _error = _load_policy_payload_with_error(raw)
    return payload


def _load_policy_payload_with_error(raw: str) -> tuple[dict, str | None]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return {}, f"json_decode:{exc.msg}"
        try:
            payload = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as inner_exc:
            return {}, f"json_decode:{inner_exc.msg}"
    return (payload if isinstance(payload, dict) else {"policies": payload}), None


def _normalize_policy_payload(
    item: dict[str, Any],
    *,
    text: str,
    context: ExtractionContext,
) -> dict[str, Any]:
    payload = dict(item)
    payload["text"] = text
    payload.setdefault("effect", "require")
    payload.setdefault("scope", {"level": "workspace"})
    payload.setdefault("valid_until", None)
    target = payload.get("target")
    payload["target"] = target if isinstance(target, dict) else {}
    obligation = payload.get("obligation")
    if not isinstance(obligation, dict):
        obligation = {"kind": _guess_obligation_kind(text), "predicate": _guess_response_predicate(text)}
    if _obligation_mentions_response(obligation):
        obligation["kind"] = "response"
        target = payload["target"]
        target["phase"] = "response"
        target["action_family"] = "message.send"
        target["action_families"] = ["message.send"]
        target.pop("tool", None)
        target["tools"] = []
    elif _required_usage_should_target_response(text, payload["target"], obligation):
        target = payload["target"]
        target["phase"] = "response"
        target["action_family"] = "message.send"
        target["action_families"] = ["message.send"]
        target.pop("tool", None)
        target["tools"] = []
    _normalize_monitor_where_values(obligation)
    _normalize_response_length_predicate(text, obligation)
    _normalize_same_step_obligation(text, payload["target"], obligation)
    _normalize_count_target(payload["target"], obligation)
    _normalize_monitor_based_response_obligation(obligation)
    _bind_broad_evidence_monitor_to_search_tools(obligation, context)
    payload["obligation"] = obligation
    _normalize_positive_obligation_effect(payload)
    return payload


def _normalize_positive_obligation_effect(payload: dict[str, Any]) -> None:
    obligation = payload.get("obligation")
    if not isinstance(obligation, dict):
        return
    if payload.get("effect") == "allow":
        return
    kind = str(obligation.get("kind") or "")
    if kind in {"prior_action", "required_tool_usage", "required_tool_evidence"}:
        payload["effect"] = "require"


def _normalize_response_length_predicate(text: str, obligation: dict[str, Any]) -> None:
    kind = str(obligation.get("kind") or "")
    if kind not in {"response", "response_format", "response_content", "response_length"}:
        return
    lower = text.lower()
    match = re.search(r"between\s+(\d+)\s+and\s+(\d+)\s+(characters?|chars?|words?)", lower)
    if match:
        low = int(match.group(1))
        high = int(match.group(2))
        unit = match.group(3)
        op = "word_count_between" if unit.startswith("word") else "char_count_between"
        obligation["predicate"] = {"field": "response", "op": op, "value": [low, high]}
        obligation.pop("op", None)
        obligation.pop("value", None)
        return
    match = re.search(r"at\s+most\s+(\d+)\s+(characters?|chars?|words?)", lower)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        op = "word_count_lte" if unit.startswith("word") else "char_count_lte"
        obligation["predicate"] = {"field": "response", "op": op, "value": value}
        obligation.pop("op", None)
        obligation.pop("value", None)
        return
    match = re.search(r"at\s+least\s+(\d+)\s+(characters?|chars?|words?)", lower)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        op = "word_count_gte" if unit.startswith("word") else "char_count_gte"
        obligation["predicate"] = {"field": "response", "op": op, "value": value}
        obligation.pop("op", None)
        obligation.pop("value", None)


def _normalize_same_step_obligation(
    text: str,
    target: dict[str, Any],
    obligation: dict[str, Any],
) -> None:
    lower = text.lower()
    if not any(token in lower for token in ("same step", "single action step", "simultaneously", "parallel")):
        return
    monitor = obligation.get("monitor")
    where = monitor.get("where") if isinstance(monitor, dict) else None
    if not isinstance(where, dict):
        return
    field = str(where.get("field") or "")
    value = where.get("value")
    if field not in {"tool", "tool_name"} or not isinstance(value, list):
        return
    required = len([item for item in value if isinstance(item, str) and item])
    if required < 2:
        if required == 1 and _looks_like_same_tool_multi_call_same_step(text):
            required = 2
            monitor["aggregate"] = "count"
            monitor.pop("distinct_by", None)
        else:
            return
    obligation["kind"] = "same_step"
    obligation["value"] = required
    obligation["op"] = "gte"
    if monitor.get("aggregate") != "count":
        monitor["aggregate"] = "distinct_count"
        monitor["distinct_by"] = "tool_name"
    monitor["group_by"] = "turn_id"
    target["phase"] = "response"
    target["action_family"] = "message.send"
    target["action_families"] = ["message.send"]
    target.pop("tool", None)
    target["tools"] = []


def _looks_like_same_tool_multi_call_same_step(text: str) -> bool:
    lower = text.lower()
    if not any(token in lower for token in ("same step", "single action step", "concurrently", "simultaneously")):
        return False
    return " and " in lower or "both" in lower or "multiple" in lower


def _normalize_count_target(target: dict[str, Any], obligation: dict[str, Any]) -> None:
    kind = str(obligation.get("kind") or "")
    if kind == "same_step":
        target["phase"] = "response"
        target["action_family"] = "message.send"
        target["action_families"] = ["message.send"]
        target.pop("tool", None)
        target["tools"] = []
        return
    if kind == "interaction_turn_count":
        target["phase"] = "response"
        target["action_family"] = "message.send"
        target["action_families"] = ["message.send"]
        target.pop("tool", None)
        target["tools"] = []
        _normalize_interaction_turn_monitor(obligation)
        return
    if kind not in {"action_count", "specific_tool_count", "tool_count"}:
        return
    op = str(obligation.get("op") or "").lower()
    if op in {"gte", "gt", "between", "range"}:
        target["phase"] = "response"
        target["action_family"] = "message.send"
        target["action_families"] = ["message.send"]
        target.pop("tool", None)
        target["tools"] = []


def _normalize_interaction_turn_monitor(obligation: dict[str, Any]) -> None:
    monitor = obligation.get("monitor")
    if not isinstance(monitor, dict):
        monitor = {}
        obligation["monitor"] = monitor
    monitor["source"] = "action_log"
    monitor["aggregate"] = "count"
    monitor["where"] = {
        "field": "action_family",
        "op": "in",
        "value": ["tool.call", "message.send"],
    }


def _normalize_monitor_based_response_obligation(obligation: dict[str, Any]) -> None:
    if str(obligation.get("kind") or "") not in {"response", "response_format", "response_content", "response_length"}:
        return
    if obligation.get("predicate") is not None:
        return
    monitor = obligation.get("monitor")
    if not isinstance(monitor, dict):
        return
    where = monitor.get("where")
    if not isinstance(where, dict):
        return
    field = str(where.get("field") or "")
    if field in {"tool", "tool_name", "action_family"}:
        obligation["kind"] = "required_tool_usage"


def _normalize_monitor_where_values(obligation: dict[str, Any]) -> None:
    monitor = obligation.get("monitor")
    if not isinstance(monitor, dict):
        return
    where = monitor.get("where")
    if not isinstance(where, dict):
        return
    if where.get("op") == "in" and isinstance(where.get("value"), str):
        values = [
            item.strip()
            for item in str(where.get("value") or "").split(",")
            if item.strip()
        ]
        if values:
            where["value"] = values


def _bind_broad_evidence_monitor_to_search_tools(
    obligation: dict[str, Any],
    context: ExtractionContext,
) -> None:
    kind = str(obligation.get("kind") or "")
    if kind not in {"required_tool_usage", "required_tool_evidence"}:
        return
    monitor = obligation.get("monitor")
    if monitor is not None and not isinstance(monitor, dict):
        return
    if monitor is not None and not _is_broad_tool_usage_monitor(monitor):
        return
    tool_names = _evidence_tool_names_from_context(context)
    if not tool_names:
        return
    obligation["monitor"] = {
        "source": "action_log",
        "where": {"field": "tool_name", "op": "in", "value": tool_names},
        "aggregate": "exists",
    }


def _is_broad_tool_usage_monitor(monitor: dict[str, Any]) -> bool:
    where = monitor.get("where")
    if where is None:
        return True
    if not isinstance(where, dict):
        return False
    field = str(where.get("field") or "")
    op = str(where.get("op") or "")
    value = where.get("value")
    if field == "action_family" and str(value) == "tool.call":
        return True
    if field != "tool_name":
        return False
    if op == "exists":
        return True
    if op == "regex" and str(value) in {".", ".*", ".+"}:
        return True
    if op in {"in", "eq"} and isinstance(value, str) and value in {"", "*", ".*", ".+", "tool.call"}:
        return True
    return False


def _evidence_tool_names_from_context(context: ExtractionContext) -> list[str]:
    raw = context.tool_capsule_system_prompt
    if not raw:
        return []
    try:
        start = raw.find("{")
        payload = json.loads(raw[start:]) if start >= 0 else {}
    except (json.JSONDecodeError, TypeError):
        return []
    names: list[str] = []
    for item in payload.get("tools", []):
        if not isinstance(item, dict):
            continue
        name = _clean_string(item.get("name"))
        if not name:
            continue
        description = _clean_string(item.get("description")) or ""
        if _looks_like_evidence_tool(name, description):
            names.append(name)
    return sorted(dict.fromkeys(names))


def _looks_like_evidence_tool(name: str, description: str) -> bool:
    haystack = f"{name} {description}".lower()
    if "send_message" in name.lower() or "message.send" in name.lower():
        return False
    evidence_markers = (
        "analy",
        "check",
        "fetch",
        "find",
        "get",
        "identifier",
        "identify",
        "locator",
        "lookup",
        "query",
        "retrieve",
        "search",
        "tracker",
        "verify",
    )
    return any(marker in haystack for marker in evidence_markers)


def _required_usage_should_target_response(
    text: str,
    target: dict[str, Any],
    obligation: dict[str, Any],
) -> bool:
    kind = str(obligation.get("kind") or "")
    if kind not in {"prior_action", "required_tool_usage", "required_tool_evidence"}:
        return False
    target_phase = str(target.get("phase") or "").lower()
    if target_phase == "response":
        return True
    lower = text.lower()
    if any(token in lower for token in ("answer", "response", "reply", "final", "information must come")):
        return True
    action_family = str(target.get("action_family") or "").lower()
    raw_action_families = target.get("action_families")
    action_families = {
        str(item).lower()
        for item in (raw_action_families if isinstance(raw_action_families, list) else [])
        if isinstance(item, str)
    }
    if action_family == "tool.call" or "tool.call" in action_families:
        monitor = obligation.get("monitor")
        where = monitor.get("where") if isinstance(monitor, dict) else None
        if not isinstance(where, dict):
            return True
        field = str(where.get("field") or "")
        value = str(where.get("value") or "")
        if field in {"tool_name", "action_family"} and value in {".*", "tool.call"}:
            return True
    return False


def _is_non_executable_policy(policy: PolicyIR) -> bool:
    obligation = policy.obligation
    if obligation.kind in {"current_action", "path_access"} and obligation.predicate is None:
        return True
    if (
        obligation.kind in {"response", "response_format", "response_content", "response_length"}
        and obligation.predicate is None
        and obligation.op is None
        and obligation.value is None
    ):
        return True
    return False


def _obligation_mentions_response(obligation: dict[str, Any]) -> bool:
    if str(obligation.get("kind") or "") in {"response", "response_format", "response_content", "response_length"}:
        return True
    predicate = obligation.get("predicate")
    if isinstance(predicate, dict) and _predicate_mentions_response(predicate):
        return True
    return False


def _predicate_mentions_response(predicate: dict[str, Any]) -> bool:
    if predicate.get("field") == "response":
        return True
    for key in ("all", "any"):
        children = predicate.get(key)
        if isinstance(children, list) and any(
            isinstance(child, dict) and _predicate_mentions_response(child)
            for child in children
        ):
            return True
    child = predicate.get("not")
    return isinstance(child, dict) and _predicate_mentions_response(child)


def _parse_ir_scope(value: dict[str, Any], context: ExtractionContext) -> Scope:
    level = str(value.get("level") or "").lower()
    if level in {"project", "phase", "occasion"}:
        scope_path = (
            _clean_string(value.get("path") or value.get("folder") or value.get("file"))
            or _clean_string(value.get("project") or value.get("phase") or value.get("name"))
        )
        if scope_path:
            return _parse_scope({**value, "level": "path", "path": scope_path}, context)
        return _default_scope(context)
    if level not in {"global", "workspace", "session", "path"}:
        level = "workspace"
    return _parse_scope({**value, "level": level}, context)


def _semantics_from_policy(policy: PolicyIR) -> RuleSemantics:
    actions = set(policy.target.action_families)
    if policy.target.tools:
        actions.add("tool.call")
    if policy.target.phase == "response":
        actions.add("message.send")
    tags = {policy.obligation.kind}
    return RuleSemantics(actions=sorted(actions), tags=sorted(tags))


def _guess_obligation_kind(text: str) -> str:
    lower = text.lower()
    if "tool" in lower and any(token in lower for token in ("at most", "no more than", "maximum")):
        return "tool_count"
    if "call" in lower or "invoke" in lower:
        return "required_tool_usage"
    return "response"


def _guess_response_predicate(text: str) -> dict[str, Any]:
    lower = text.lower()
    if "json" in lower:
        return {"field": "response", "op": "json_object", "value": {}}
    if "markdown" in lower and "no markdown" not in lower and "plain text" not in lower:
        return {"field": "response", "op": "regex", "value": r"(\\*\\*|#|\\[.+\\]\\(.+\\)|[-*]\\s)"}
    if "plain text" in lower or "no markdown" in lower:
        return {"field": "response", "op": "not_regex", "value": r"(\\*\\*|#|\\[.+\\]\\(.+\\)|[-*]\\s)"}
    return {"field": "response", "op": "exists"}


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
