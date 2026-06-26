from __future__ import annotations

from datetime import datetime

from memory_as_contracts.extractor import (
    CONTRACT_EXTRACTION_SYSTEM_PROMPT,
    PERIODIC_EXTRACTION_USER_TURN_INTERVAL,
    CandidateJsonContractExtractor,
    ExtractionContext,
    HeuristicContractExtractor,
)
from memory_as_contracts.models import (
    ContractKind,
    LifecycleType,
    Modality,
    ScopeLevel,
    SourceKind,
    ValidatorEnforcementShape,
)
from memory_as_contracts.normalizers import LifecycleNormalizer, NormalizationContext, ScopeNormalizer


def context() -> ExtractionContext:
    return ExtractionContext(
        normalization=NormalizationContext(
            workspace="/workspace/project",
            repo="project",
            agent_family=["codex"],
            timezone="Asia/Hong_Kong",
            now=datetime(2026, 5, 23, 9, 30),
        ),
        conversation_id="conv-1",
        turn_id="u-1",
    )


def test_online_extraction_collects_user_turns_only() -> None:
    extractor = HeuristicContractExtractor()

    user_contracts = extractor.extract_online_turn(
        role="user",
        text="This week, do not push any code changes to Git before asking me.",
        context=context(),
    )
    assistant_contracts = extractor.extract_online_turn(
        role="assistant",
        text="I will never push without asking.",
        context=context(),
    )

    assert len(user_contracts) == 1
    assert assistant_contracts == []
    contract = user_contracts[0]
    assert contract.kind == ContractKind.PROHIBITION
    assert contract.modality == Modality.MUST_NOT
    assert contract.source.kind == SourceKind.USER_TURN
    assert contract.scope.level == ScopeLevel.PROJECT
    assert contract.lifecycle.type == LifecycleType.BOUNDED_TIME
    assert contract.lifecycle.expires_at is not None
    assert contract.lifecycle.expires_at.tzinfo is not None


def test_heuristic_extraction_splits_mixed_agent_working_turns() -> None:
    extractor = HeuristicContractExtractor()

    contracts = extractor.extract_online_turn(
        role="user",
        text=(
            "For this repo, do not run git push unless I explicitly approve it, "
            "and prefer risk-first summaries when reporting release work."
        ),
        context=context(),
    )

    assert [contract.kind for contract in contracts] == [
        ContractKind.PROHIBITION,
        ContractKind.PREFERENCE,
    ]
    assert all(contract.scope.level == ScopeLevel.PROJECT for contract in contracts)


def test_heuristic_extraction_binds_web_search_and_message_actions() -> None:
    extractor = HeuristicContractExtractor()

    web_contract = extractor.extract_online_turn(
        role="user",
        text="For this repo, do not use web search without asking me first.",
        context=context(),
    )[0]
    message_contract = extractor.extract_online_turn(
        role="user",
        text="For this session, do not send messages to external channels without asking me.",
        context=context(),
    )[0]

    assert "web.search" in web_contract.semantics.actions
    assert "network_read" in web_contract.semantics.tags
    assert "message.send" in message_contract.semantics.actions
    assert "notify_human" in message_contract.semantics.tags


def test_heuristic_extraction_binds_publish_clause() -> None:
    contract = HeuristicContractExtractor().extract_online_turn(
        role="user",
        text="Do not publish anything yet.",
        context=context(),
    )[0]

    assert contract.kind == ContractKind.PROHIBITION
    assert "git.push" in contract.semantics.actions
    assert "publish_code" in contract.semantics.tags


def test_heuristic_extraction_classifies_check_only_validator_shape() -> None:
    contract = HeuristicContractExtractor().extract_online_turn(
        role="user",
        text="For this repo, before git push, run tests.",
        context=context(),
    )[0]

    assert contract.validator_enforcement_shape == ValidatorEnforcementShape.CHECK_ONLY
    assert contract.check_patterns
    assert contract.update_patterns == []
    assert contract.state_fields == []


def test_heuristic_extraction_classifies_check_update_validator_shape() -> None:
    contract = HeuristicContractExtractor().extract_online_turn(
        role="user",
        text="For this task, total cost must not exceed $90.",
        context=context(),
    )[0]

    assert contract.validator_enforcement_shape == ValidatorEnforcementShape.CHECK_UPDATE
    assert contract.check_patterns
    assert contract.update_patterns
    assert {"spent_cents", "seen_entry_seqs"}.issubset(set(contract.state_fields))


def test_cold_start_preserves_source_and_path() -> None:
    extractor = HeuristicContractExtractor()

    contracts = extractor.extract_cold_start_source(
        text="Do not edit files under vendor/**.",
        source_kind=SourceKind.PROJECT_DOC,
        context=context(),
        path="AGENTS.md",
        fingerprint="abc",
    )

    assert len(contracts) == 1
    assert contracts[0].source.kind == SourceKind.PROJECT_DOC
    assert contracts[0].source.path == "AGENTS.md"
    assert contracts[0].scope.level == ScopeLevel.PROJECT
    assert contracts[0].scope.project == "project"


def test_user_turn_ignores_single_turn_instruction_by_default() -> None:
    extractor = HeuristicContractExtractor()

    contracts = extractor.extract_online_turn(
        role="user",
        text="In this answer, use short bullets.",
        context=context(),
    )

    assert contracts == []


def test_llm_user_turn_prompt_is_fixed_but_cold_start_prompt_is_adapter_owned() -> None:
    prompts: list[str] = []

    def response_provider(prompt: str) -> str:
        prompts.append(prompt)
        return '{"contracts":[]}'

    def cold_start_prompt(text: str, source_kind: SourceKind) -> str:
        return f"CUSTOM {source_kind.value}: {text}"

    extractor = CandidateJsonContractExtractor(
        response_provider,
        cold_start_prompt_builder=cold_start_prompt,
    )

    extractor.extract_online_turn(role="user", text="For this repo, use uv.", context=context())
    extractor.extract_cold_start_source(
        text="Do not edit files under vendor/**.",
        source_kind=SourceKind.PROJECT_DOC,
        context=context(),
        path="AGENTS.md",
    )

    # Simple providers receive the system contract spec folded in ahead of the user body.
    assert "confidence" not in prompts[0].lower()
    assert "scoped beyond the current turn" in prompts[0]
    assert "validator_enforcement_shape" in prompts[0]
    assert "check_patterns" in prompts[0]
    assert "update_patterns" in prompts[0]
    assert "state keys maintained by check_update validators" in prompts[0]
    assert "native tool patterns for pending actions" in prompts[0]
    assert "Extract candidate contracts that agent must obey" in prompts[0]
    assert prompts[0].rstrip().endswith("Source text:\nFor this repo, use uv.")
    assert prompts[1].endswith("CUSTOM project_doc: Do not edit files under vendor/**.")


def test_llm_extractor_puts_tools_in_user_prompt_and_rules_in_system() -> None:
    seen: dict[str, str | None] = {}

    def response_provider(prompt: str, *, system_prompt: str | None = None) -> str:
        seen["prompt"] = prompt
        seen["system_prompt"] = system_prompt
        return '{"contracts":[]}'

    extraction_context = ExtractionContext(
        normalization=context().normalization,
        conversation_id="conv-1",
        turn_id="u-1",
        tool_capsule_system_prompt=(
            "Tool definitions available to the acting agent are read-only.\n"
            '{"tools":[{"name":"exec_command","input_schema":{"required":["cmd"]}}]}'
        ),
        similar_rules_system_prompt=(
            "Existing similar rules; do not re-emit duplicates.\n"
            "1. [MAC-existing] prohibition scope=repo: Do not push without approval."
        ),
    )

    CandidateJsonContractExtractor(response_provider).extract_online_turn(
        role="user",
        text="For this repo, do not push without asking.",
        context=extraction_context,
    )

    prompt = seen["prompt"] or ""
    system_prompt = seen["system_prompt"] or ""

    # All requirements live in the static system prompt.
    assert "A MAC contract is" in system_prompt
    assert "final effective form" in system_prompt
    assert "internally resolve duplicates, conflicts" in system_prompt
    assert "exec_command" not in system_prompt
    assert "MAC-existing" not in system_prompt

    # The user prompt only carries tool capsules (at the very top), similar rules, and source.
    assert prompt.startswith("Tool definitions available to the acting agent are read-only.")
    assert "exec_command" in prompt
    assert "MAC-existing" in prompt
    assert "Source text:" in prompt
    assert prompt.index("exec_command") < prompt.index(
        "Extract candidate contracts that agent must obey"
    )


def test_llm_extractor_folds_system_into_prompt_for_simple_providers() -> None:
    prompts: list[str] = []

    def response_provider(prompt: str) -> str:
        prompts.append(prompt)
        return '{"contracts":[]}'

    extraction_context = ExtractionContext(
        normalization=context().normalization,
        tool_capsule_system_prompt='{"tools":[{"name":"Bash"}]}',
    )

    CandidateJsonContractExtractor(response_provider).extract_online_turn(
        role="user",
        text="For this repo, do not push without asking.",
        context=extraction_context,
    )

    # Providers without a system-prompt kwarg receive the system spec folded ahead of the body.
    assert "A MAC contract is" in prompts[0]
    assert '"name":"Bash"' in prompts[0]
    assert "Source text:" in prompts[0]


def test_llm_extractor_reads_only_canonical_semantics_scope_and_check_patterns() -> None:
    def response_provider(prompt: str) -> str:
        assert "tool_patterns" not in prompt
        assert "scope" in prompt
        assert "check_patterns" in prompt
        assert "native tool name" in prompt
        return r'''
        {"contracts": [{
          "text": "For this repo, do not use web search without asking me first.",
          "effect": "deny",
          "scope": {"level": "project", "project": "project"},
          "kind": "prohibition",
          "modality": "MUST_NOT",
          "strength": "hard",
          "semantics": {
            "actions": ["web.search"],
            "tags": ["network_read"]
          },
          "check_patterns": [{
            "tool": "web.search",
            "args": {}
          }]
        }]}
        '''

    contracts = CandidateJsonContractExtractor(response_provider).extract_online_turn(
        role="user",
        text="For this repo, do not use web search without asking me first.",
        context=context(),
    )

    contract = contracts[0]
    assert contract.semantics.actions == ["web.search"]
    assert contract.semantics.tags == ["network_read"]
    assert contract.scope.level == ScopeLevel.PROJECT
    assert contract.scope.project == "project"
    assert any(pattern.tool == "web.search" for pattern in contract.check_patterns)


def test_llm_extractor_downgrades_direct_rule_from_spurious_validator_shape() -> None:
    def response_provider(prompt: str) -> str:
        return r'''
        {"contracts": [{
          "text": "For this repo, never edit files under generated/**.",
          "effect": "deny",
          "scope": {"level": "project", "project": "project"},
          "validator_enforcement_shape": "check_only",
          "check_patterns": [{
            "tool": "apply_patch",
            "args": {"patch": {"mentions_path_glob": "generated/**"}}
          }],
          "update_patterns": [],
          "state_fields": []
        }]}
        '''

    contract = CandidateJsonContractExtractor(response_provider).extract_online_turn(
        role="user",
        text="For this repo, never edit files under generated/**.",
        context=context(),
    )[0]

    assert contract.validator_enforcement_shape == ValidatorEnforcementShape.NO_VALIDATOR
    assert contract.check_patterns == []


def test_scope_and_lifecycle_normalizers_ground_relative_fields() -> None:
    normalization = context().normalization

    scope = ScopeNormalizer().normalize("For this task, ask before sending email.", normalization)
    lifecycle = LifecycleNormalizer().normalize("Today do not push.", normalization)

    assert scope.level == ScopeLevel.PROJECT
    assert lifecycle.type == LifecycleType.BOUNDED_TIME
    assert lifecycle.expires_at is not None
    assert lifecycle.expires_at.hour == 23


def test_scope_normalizer_supports_session_and_module_scope() -> None:
    normalization = context().normalization

    session_scope = ScopeNormalizer().normalize("For this session, use short bullets.", normalization)
    module_scope = ScopeNormalizer().normalize(
        "For component auth, do not edit generated files.",
        normalization,
    )

    assert session_scope.level == ScopeLevel.SESSION
    assert module_scope.level == ScopeLevel.MODULE
    assert module_scope.module == "auth"


def test_scope_normalizer_does_not_treat_workspace_as_path() -> None:
    normalization = context().normalization

    workspace_scope = ScopeNormalizer().normalize(
        "For this repo, do not use web search in the workspace.",
        normalization,
    )
    generated_scope = ScopeNormalizer().normalize(
        "Do not touch generated manifests while doing this.",
        normalization,
    )

    assert workspace_scope.level == ScopeLevel.PROJECT
    assert generated_scope.level == ScopeLevel.PROJECT


def test_scope_normalizer_extracts_bare_filename_targets() -> None:
    scope = ScopeNormalizer().normalize(
        "Do not edit package-lock.json without asking.",
        context().normalization,
    )

    assert scope.level == ScopeLevel.PROJECT


def test_scope_normalizer_preserves_inline_relative_paths() -> None:
    scope = ScopeNormalizer().normalize(
        "Do not edit docs/archive.md.",
        context().normalization,
    )

    assert scope.level == ScopeLevel.PROJECT


def test_mixed_task_turn_targets_negated_bare_filename() -> None:
    contracts = HeuristicContractExtractor().extract_online_turn(
        role="user",
        text=(
            "Update package.json for the local script change, "
            "but do not edit package-lock.json; keep the summary concise."
        ),
        context=context(),
    )

    assert len(contracts) == 1
    assert contracts[0].text == "do not edit package-lock.json"
    assert contracts[0].scope.level == ScopeLevel.PROJECT


def test_live_extraction_system_prompt_defines_rule_boundaries() -> None:
    assert "A MAC contract is" in CONTRACT_EXTRACTION_SYSTEM_PROMPT
    assert "Do not extract" in CONTRACT_EXTRACTION_SYSTEM_PROMPT
    assert "Duplicate paraphrases" in CONTRACT_EXTRACTION_SYSTEM_PROMPT
    assert "Meta-statements about possible future exceptions" in CONTRACT_EXTRACTION_SYSTEM_PROMPT
    assert PERIODIC_EXTRACTION_USER_TURN_INTERVAL == 10
