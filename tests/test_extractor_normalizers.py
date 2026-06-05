from __future__ import annotations

from datetime import datetime

from memory_as_contracts.extractor import (
    CONTRACT_EXTRACTION_SYSTEM_PROMPT,
    PERIODIC_EXTRACTION_USER_TURN_INTERVAL,
    CandidateJsonContractExtractor,
    ExtractionContext,
    HeuristicContractExtractor,
)
from memory_as_contracts.models import ContractKind, LifecycleType, Modality, ScopeLevel, SourceKind
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
    assert all(contract.scope.level == ScopeLevel.REPO for contract in contracts)


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

    assert "web.search" in web_contract.action_constraints.host_actions
    assert "network_read" in web_contract.action_constraints.canonical_tags
    assert "message.send" in message_contract.action_constraints.host_actions
    assert "notify_human" in message_contract.action_constraints.canonical_tags


def test_heuristic_extraction_binds_publish_clause() -> None:
    contract = HeuristicContractExtractor().extract_online_turn(
        role="user",
        text="Do not publish anything yet.",
        context=context(),
    )[0]

    assert contract.kind == ContractKind.PROHIBITION
    assert "git.push" in contract.action_constraints.host_actions
    assert "publish_code" in contract.action_constraints.canonical_tags


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
    assert contracts[0].scope.level == ScopeLevel.PATH
    assert contracts[0].scope.path_globs == ["vendor/**"]


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

    assert "fixed user-turn extraction policy" in prompts[0]
    assert "confidence" not in prompts[0].lower()
    assert prompts[1] == "CUSTOM project_doc: Do not edit files under vendor/**."


def test_llm_extractor_injects_tool_capsules_as_system_prompt() -> None:
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
    )

    CandidateJsonContractExtractor(response_provider).extract_online_turn(
        role="user",
        text="For this repo, do not push without asking.",
        context=extraction_context,
    )

    assert "A MAC contract is" in (seen["system_prompt"] or "")
    assert "exec_command" in (seen["system_prompt"] or "")
    assert "Source text:" in (seen["prompt"] or "")


def test_llm_extractor_falls_back_to_prompt_injection_for_simple_providers() -> None:
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

    assert "Additional system context" in prompts[0]
    assert '"name":"Bash"' in prompts[0]


def test_llm_extractor_treats_predicate_hints_as_non_authoritative() -> None:
    def response_provider(prompt: str) -> str:
        assert "tool_patterns" in prompt
        assert "native tool name" in prompt
        return r'''
        {"contracts": [{
          "text": "For this repo, do not use web search without asking me first.",
          "source_span": "do not use web search without asking me first",
          "kind": "prohibition",
          "modality": "MUST_NOT",
          "strength": "hard",
          "action_constraints": {
            "host_actions": ["web.search"],
            "canonical_tags": ["network_read"]
          },
          "predicate_hints": {
            "host_action_patterns": [{
              "host_action": "exec",
              "tool_name": "exec",
              "parameter_regex": {"cmd": "^.*(curl|wget|search|browser|fetch).*$"}
            }]
          }
        }]}
        '''

    contracts = CandidateJsonContractExtractor(response_provider).extract_online_turn(
        role="user",
        text="For this repo, do not use web search without asking me first.",
        context=context(),
    )

    contract = contracts[0]
    assert contract.action_constraints.host_actions == ["web.search"]
    assert contract.compiled_predicates is None
    assert any(pattern.tool == "web.search" for pattern in contract.tool_patterns)


def test_scope_and_lifecycle_normalizers_ground_relative_fields() -> None:
    normalization = context().normalization

    scope = ScopeNormalizer().normalize("For this task, always ask before sending email.", normalization)
    lifecycle = LifecycleNormalizer().normalize("Today do not push.", normalization)

    assert scope.level == ScopeLevel.TASK
    assert lifecycle.type == LifecycleType.BOUNDED_TIME
    assert lifecycle.expires_at is not None
    assert lifecycle.expires_at.hour == 23


def test_scope_normalizer_supports_per_turn_and_component_scope() -> None:
    normalization = context().normalization

    per_turn_scope = ScopeNormalizer().normalize("In this answer, use short bullets.", normalization)
    component_scope = ScopeNormalizer().normalize(
        "For component auth, do not edit generated files.",
        normalization,
    )

    assert per_turn_scope.level == ScopeLevel.PER_TURN
    assert component_scope.level == ScopeLevel.COMPONENT
    assert component_scope.component == "auth"


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

    assert workspace_scope.level == ScopeLevel.REPO
    assert workspace_scope.path_globs == []
    assert generated_scope.level == ScopeLevel.PATH
    assert generated_scope.path_globs == ["generated/**"]


def test_scope_normalizer_extracts_bare_filename_targets() -> None:
    scope = ScopeNormalizer().normalize(
        "Do not edit package-lock.json without asking.",
        context().normalization,
    )

    assert scope.level == ScopeLevel.PATH
    assert scope.path_globs == ["package-lock.json"]


def test_scope_normalizer_preserves_inline_relative_paths() -> None:
    scope = ScopeNormalizer().normalize(
        "Do not edit docs/archive.md.",
        context().normalization,
    )

    assert scope.level == ScopeLevel.PATH
    assert scope.path_globs == ["docs/archive.md"]


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
    assert contracts[0].scope.level == ScopeLevel.PATH
    assert contracts[0].scope.path_globs == ["package-lock.json"]


def test_live_extraction_system_prompt_defines_rule_boundaries() -> None:
    assert "A MAC contract is" in CONTRACT_EXTRACTION_SYSTEM_PROMPT
    assert "Do not extract" in CONTRACT_EXTRACTION_SYSTEM_PROMPT
    assert "Duplicate paraphrases" in CONTRACT_EXTRACTION_SYSTEM_PROMPT
    assert "Meta-statements about possible future exceptions" in CONTRACT_EXTRACTION_SYSTEM_PROMPT
    assert PERIODIC_EXTRACTION_USER_TURN_INTERVAL == 10
