from __future__ import annotations

from datetime import datetime, timezone

import pytest
from openai import APIConnectionError, APITimeoutError

from memory_as_contracts.extractor import (
    CandidateJsonContractExtractor,
    ExtractionContext,
    OpenAIChatResponseProvider,
)
from memory_as_contracts.gate import ActionGate
from memory_as_contracts.models import (
    Contract,
    ContractKind,
    ContractStatus,
    EdgeRelation,
    GateDecisionType,
    SourceKind,
)
from memory_as_contracts.normalizers import NormalizationContext
from memory_as_contracts.resolver import ConflictResolver, RELATION_CLASSIFICATION_SYSTEM_PROMPT
from memory_as_contracts.signatures import ActionSignatureBuilder, SignatureContext
from memory_as_contracts.store import ContractStore


pytestmark = pytest.mark.live_llm


PROJECT_DOC = """
Project operating notes:
- For release work, always push release branches after tests pass.
- Never edit files under generated/**.
- Do not edit files under generated/** unless a narrower task exception says so.
"""


USER_TURN = """
For this repo, correction to the release habit: do not push any Git changes unless I
explicitly say "ship it".
This repeats the same rule in different words: do not run git push until I approve it.
Exception for this task only: you may edit files under generated/sandbox/**, but
generated/** remains protected everywhere else.
When reporting release work, start with the risk first and then the patch details;
I scan that faster.
"""


def test_live_llm_effectiveness_boundary_for_overlap_conflict_duplicates_and_preferences() -> None:
    provider = _live_provider_or_skip()
    extractor = CandidateJsonContractExtractor(provider)
    context = ExtractionContext(
        normalization=NormalizationContext(
            workspace="/workspace/project",
            repo="project",
            task="release-task",
            agent_family=["codex"],
            timezone="Asia/Hong_Kong",
            now=datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc),
        ),
        conversation_id="conv-effect",
        turn_id="u-effect",
    )

    try:
        project_contracts = extractor.extract_cold_start_source(
            text=PROJECT_DOC,
            source_kind=SourceKind.PROJECT_DOC,
            context=context,
            path="AGENTS.md",
            fingerprint="effect-project-doc",
        )
        user_contracts = extractor.extract_online_turn(
            role="user",
            text=USER_TURN,
            context=context,
        )
    except (APIConnectionError, APITimeoutError) as exc:
        pytest.skip(f"live LLM endpoint unavailable: {exc}")
    all_contracts = project_contracts + user_contracts
    diagnostics = _diagnostics(all_contracts)

    assert len(project_contracts) >= 2, diagnostics
    assert len(user_contracts) >= 3, diagnostics
    assert any(
        contract.kind in {ContractKind.PREFERENCE, ContractKind.PROCEDURE}
        and "risk" in contract.text.lower()
        and "patch" in contract.text.lower()
        for contract in user_contracts
    ), diagnostics
    assert any(contract.kind == ContractKind.EXCEPTION for contract in user_contracts), diagnostics

    store = ContractStore(":memory:")
    store.init_db()
    relation_provider = OpenAIChatResponseProvider.from_env(
        system_prompt=RELATION_CLASSIFICATION_SYSTEM_PROMPT
    )
    resolver = ConflictResolver(store, relation_response_provider=relation_provider)
    for contract in all_contracts:
        resolver.insert(contract)

    edges = store.list_edges()
    edge_relations = {edge.relation for edge in edges}
    assert EdgeRelation.EXCEPTION_TO in edge_relations, _diagnostics(store.list_contracts())

    builder = ActionSignatureBuilder()
    signature_context = SignatureContext(
        session_id="sess-effect",
        task_id="release-task",
        cwd="/workspace/project",
        repo="project",
        branch="release",
        now=datetime(2026, 5, 23, 10, 15, tzinfo=timezone.utc),
    )
    gate = ActionGate(store)

    sandbox_write = builder.build(
        tool_name="file.write",
        raw_arguments={"path": "generated/sandbox/demo.py"},
        intent="edit generated sandbox fixture",
        context=signature_context,
    )
    protected_write = builder.build(
        tool_name="file.write",
        raw_arguments={"path": "generated/core.py"},
        intent="edit generated core file",
        context=signature_context,
    )
    git_push = builder.build(
        tool_name="exec",
        raw_arguments={"cmd": "git push origin release"},
        intent="publish release branch",
        context=signature_context,
    )

    sandbox_result = gate.gate(sandbox_write)
    protected_result = gate.gate(protected_write)
    push_result = gate.gate(git_push)

    assert sandbox_result.decision.decision == GateDecisionType.ALLOW, (
        sandbox_result.decision,
        _diagnostics(store.list_contracts([ContractStatus.ACTIVE, ContractStatus.PENDING_CONFLICT])),
    )
    assert protected_result.decision.decision in {
        GateDecisionType.BLOCK,
    }, protected_result.decision
    assert push_result.decision.decision in {
        GateDecisionType.BLOCK,
    }, push_result.decision
    assert EdgeRelation.CONFLICTS_WITH in edge_relations or push_result.decision.decision in {
        GateDecisionType.BLOCK,
    }, _diagnostics(store.list_contracts())
    assert edge_relations.intersection(
        {EdgeRelation.DUPLICATE, EdgeRelation.REFINEMENT}
    ) or len(_git_push_related(user_contracts)) == 1, _diagnostics(store.list_contracts())
    assert any(
        ignored.reason == "exception_applied"
        for receipt in store.list_receipts()
        for ignored in receipt.contracts_ignored
    ), [receipt.model_dump(mode="json") for receipt in store.list_receipts()]


def _live_provider_or_skip() -> OpenAIChatResponseProvider:
    try:
        return OpenAIChatResponseProvider.from_env()
    except ValueError as exc:
        pytest.skip(str(exc))


def _diagnostics(contracts: list[Contract]) -> list[dict]:
    return [
        {
            "id": contract.id,
            "text": contract.text,
            "kind": contract.kind.value,
            "modality": contract.modality.value,
            "status": contract.status.value,
            "source": contract.source.kind.value,
            "scope": contract.scope.model_dump(mode="json"),
            "semantics": contract.semantics.model_dump(mode="json"),
            "tool_patterns": [pattern.model_dump(mode="json") for pattern in contract.tool_patterns],
            "targets": [target.model_dump(mode="json") for target in contract.targets],
        }
        for contract in contracts
    ]


def _git_push_related(contracts: list[Contract]) -> list[Contract]:
    return [
        contract
        for contract in contracts
        if "push" in contract.text.lower() or "git" in contract.text.lower()
    ]
