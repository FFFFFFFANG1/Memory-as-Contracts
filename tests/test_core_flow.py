from __future__ import annotations

from datetime import datetime, timezone

from memory_as_contracts.ambiguity import AmbiguityMonitor, LLMPredicateRefiner
from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.gate import ActionGate, ExcludedActionPattern
from memory_as_contracts.models import (
    ActionConstraints,
    CompiledPredicateVersion,
    Contract,
    ContractEdge,
    ContractKind,
    ContractSource,
    ContractStatus,
    EdgeRelation,
    HostActionPattern,
    JobStatus,
    Lifecycle,
    LifecycleType,
    MatchOutcome,
    Modality,
    PredicateEvaluation,
    PredicateStatus,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
)
from memory_as_contracts.resolver import ConflictResolver
from memory_as_contracts.retrieval import (
    DEFAULT_PROMPT_TOKEN_BUDGET,
    PromptIntakeRetriever,
    PromptRetrievalContext,
)
from memory_as_contracts.signatures import ActionSignatureBuilder, SignatureContext, coding_available_actions
from memory_as_contracts.store import ContractStore


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


def project_scope(workspace: str = "/workspace/project") -> Scope:
    return Scope(level=ScopeLevel.PROJECT, workspace=workspace, repo="project")


def path_scope(path_glob: str, workspace: str = "/workspace/project") -> Scope:
    return Scope(
        level=ScopeLevel.PATH,
        workspace=workspace,
        repo="project",
        path_globs=[path_glob],
    )


def source(kind: SourceKind = SourceKind.USER_TURN) -> ContractSource:
    return ContractSource(
        kind=kind,
        span="do not push",
        created_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
    )


def push_prohibition(contract_id: str = "MAC-push") -> Contract:
    return Contract(
        id=contract_id,
        text="Do not push any code changes to Git before asking me.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=source(),
        scope=project_scope(),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        action_constraints=ActionConstraints(
            host_actions=["git.push"],
            canonical_tags=["external_write", "publish_code"],
        ),
    )


def push_prohibition_from_source(
    contract_id: str,
    source_kind: SourceKind,
    text: str = "Do not push any code changes to Git before asking me.",
) -> Contract:
    return push_prohibition(contract_id).model_copy(
        update={"text": text, "source": source(source_kind)}
    )


def preference(contract_id: str, text: str) -> Contract:
    return Contract(
        id=contract_id,
        text=text,
        kind=ContractKind.PREFERENCE,
        modality=Modality.SHOULD,
        strength=Strength.SOFT,
        source=source(SourceKind.USER_PROFILE),
        scope=Scope(level=ScopeLevel.GLOBAL, user_id="user-1"),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
    )


def file_rule(
    contract_id: str,
    *,
    text: str,
    kind: ContractKind,
    modality: Modality,
    path_glob: str,
    source_kind: SourceKind = SourceKind.USER_TURN,
    lifecycle_type: LifecycleType = LifecycleType.UNTIL_REVOKED,
    host_action: str = "file.write",
    tag: str = "file_write",
) -> Contract:
    return Contract(
        id=contract_id,
        text=text,
        kind=kind,
        modality=modality,
        strength=Strength.HARD,
        source=source(source_kind),
        scope=path_scope(path_glob),
        lifecycle=Lifecycle(
            type=lifecycle_type,
            until_revoked=lifecycle_type == LifecycleType.UNTIL_REVOKED,
        ),
        action_constraints=ActionConstraints(
            host_actions=[host_action],
            canonical_tags=[tag],
        ),
    )


def git_push_signature():
    return ActionSignatureBuilder().build(
        tool_name="exec",
        raw_arguments={"cmd": "git push origin main"},
        intent="publish code",
        context=SignatureContext(
            session_id="sess-1",
            cwd="/workspace/project",
            repo="project",
            branch="main",
            now=datetime(2026, 5, 23, 10, tzinfo=timezone.utc),
        ),
    )


def test_signature_builder_and_policy_compiler_match_git_push() -> None:
    signature = git_push_signature()
    contract = push_prohibition()
    predicate = PolicyCompiler().compile(contract, signature.available_actions)

    assert signature.host_action == "git.push"
    assert "publish_code" in signature.canonical_tags
    assert PolicyCompiler().evaluate(predicate, signature) == MatchOutcome.MATCHED


def test_policy_compiler_evaluates_exact_tool_name_and_parameter_regex() -> None:
    compiler = PolicyCompiler()
    predicate = CompiledPredicateVersion(
        host_action_patterns=[
            HostActionPattern(
                action="git.push",
                tool_name="exec",
                parameter_regex={"cmd": r"^git\s+push(\s|$)"},
            )
        ]
    )
    push_signature = git_push_signature()
    status_signature = ActionSignatureBuilder().build(
        tool_name="exec",
        raw_arguments={"cmd": "git status --short"},
        context=SignatureContext(
            session_id="sess-1",
            cwd="/workspace/project",
            repo="project",
            now=datetime(2026, 5, 23, 10, tzinfo=timezone.utc),
        ),
    )

    assert compiler.evaluate(predicate, push_signature) == MatchOutcome.MATCHED
    assert compiler.evaluate(predicate, status_signature) == MatchOutcome.NOT_MATCHED


def test_policy_compiler_does_not_overblock_generic_exec_for_git_push_rule() -> None:
    compiler = PolicyCompiler()
    contract = push_prohibition()
    builder = ActionSignatureBuilder()
    context = SignatureContext(session_id="sess-1", cwd="/workspace/project", repo="project")

    predicate = compiler.compile(contract, builder.build(
        tool_name="exec",
        raw_arguments={"cmd": "git push origin main"},
        context=context,
    ).available_actions)
    status_signature = builder.build(
        tool_name="exec",
        raw_arguments={"cmd": "git status --short"},
        context=context,
    )
    file_signature = builder.build(
        tool_name="file.write",
        raw_arguments={"path": "src/app.py"},
        context=context,
    )

    assert compiler.evaluate(predicate, status_signature) == MatchOutcome.NOT_MATCHED
    assert compiler.evaluate(predicate, file_signature) == MatchOutcome.NOT_MATCHED


def test_policy_compiler_targets_bare_filename_rules() -> None:
    contract = Contract(
        id="MAC-lock",
        text="Do not edit package-lock.json without asking.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=source(),
        scope=path_scope("package-lock.json"),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        action_constraints=ActionConstraints(
            host_actions=["file.write"],
            canonical_tags=["file_write"],
        ),
    )
    builder = ActionSignatureBuilder()
    context = SignatureContext(session_id="sess-1", cwd="/workspace/project", repo="project")
    predicate = PolicyCompiler().compile(contract, context.available_actions)
    package_json = builder.build(
        tool_name="file.write",
        raw_arguments={"path": "package.json"},
        context=context,
    )
    package_lock = builder.build(
        tool_name="file.write",
        raw_arguments={"path": "package-lock.json"},
        context=context,
    )

    assert PolicyCompiler().evaluate(predicate, package_json) == MatchOutcome.NOT_MATCHED
    assert PolicyCompiler().evaluate(predicate, package_lock) == MatchOutcome.MATCHED


def test_policy_compiler_prefers_negated_bare_filename_target() -> None:
    contract = Contract(
        id="MAC-lock",
        text="Update package.json, but do not edit package-lock.json.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=source(),
        scope=path_scope("package-lock.json"),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        action_constraints=ActionConstraints(
            host_actions=["file.write"],
            canonical_tags=["file_write"],
        ),
    )
    builder = ActionSignatureBuilder()
    context = SignatureContext(session_id="sess-1", cwd="/workspace/project", repo="project")
    predicate = PolicyCompiler().compile(contract, context.available_actions)

    assert PolicyCompiler().evaluate(
        predicate,
        builder.build(
            tool_name="file.write",
            raw_arguments={"path": "package.json"},
            context=context,
        ),
    ) == MatchOutcome.NOT_MATCHED
    assert PolicyCompiler().evaluate(
        predicate,
        builder.build(
            tool_name="file.write",
            raw_arguments={"path": "package-lock.json"},
            context=context,
        ),
    ) == MatchOutcome.MATCHED


def test_policy_compiler_grounds_bare_filename_to_workspace_path(tmp_path) -> None:
    workspace = tmp_path / "repo"
    (workspace / "docs").mkdir(parents=True)
    (workspace / "docs" / "archive.md").write_text("archived", encoding="utf-8")
    contract = file_rule(
        "MAC-archive",
        text="Do not edit archive.md.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        path_glob="archive.md",
    ).model_copy(update={"scope": path_scope("archive.md", str(workspace))})
    predicate = PolicyCompiler().compile(contract, coding_available_actions())
    builder = ActionSignatureBuilder()
    context = SignatureContext(session_id="sess-1", cwd=str(workspace), repo="repo")

    assert [target.value for target in predicate.target_patterns] == ["docs/archive.md"]
    assert PolicyCompiler().evaluate(
        predicate,
        builder.build(
            tool_name="file.write",
            raw_arguments={"path": "docs/archive.md"},
            context=context,
        ),
    ) == MatchOutcome.MATCHED


def test_policy_compiler_expands_lockfile_category_without_blocking_manifest(tmp_path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "package-lock.json").write_text("{}", encoding="utf-8")
    contract = Contract(
        id="MAC-lockfiles",
        text="Do not modify lockfiles.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=source(),
        scope=project_scope(str(workspace)),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        action_constraints=ActionConstraints(
            host_actions=["file.write"],
            canonical_tags=["file_write"],
        ),
    )
    predicate = PolicyCompiler().compile(contract, coding_available_actions())
    builder = ActionSignatureBuilder()
    context = SignatureContext(session_id="sess-1", cwd=str(workspace), repo="repo")

    assert "package-lock.json" in {target.value for target in predicate.target_patterns}
    assert PolicyCompiler().evaluate(
        predicate,
        builder.build(
            tool_name="file.write",
            raw_arguments={"path": "package.json"},
            context=context,
        ),
    ) == MatchOutcome.NOT_MATCHED
    assert PolicyCompiler().evaluate(
        predicate,
        builder.build(
            tool_name="file.write",
            raw_arguments={"path": "package-lock.json"},
            context=context,
        ),
    ) == MatchOutcome.MATCHED


def test_policy_compiler_grounds_llm_hint_before_gate_uses_it() -> None:
    store = make_store()
    hint = CompiledPredicateVersion(
        id="PV-raw",
        contract_id="MAC-push",
        host_action_patterns=[
            HostActionPattern(
                action="exec",
                tool_name="exec",
                parameter_regex={"cmd": "git push"},
            )
        ],
    )
    store.add_contract(push_prohibition("MAC-push").model_copy(update={"compiled_predicates": hint}))

    result = ActionGate(store).gate(git_push_signature())
    grounded = store.get_contract("MAC-push").compiled_predicates

    assert result.decision.decision.value == "block"
    assert grounded.id != "PV-raw"
    assert grounded.host_action_patterns[0].action == "git.push"
    assert grounded.host_action_patterns[0].parameter_regex["cmd"] == r"^git\s+push(\s|$)"


def test_signature_builder_supports_external_message_action() -> None:
    signature = ActionSignatureBuilder().build(
        tool_name="message.send",
        raw_arguments={"channel": "slack", "text": "Run failed"},
        intent="notify Slack",
        context=SignatureContext(session_id="sess-1", cwd="/workspace/project", repo="project"),
    )

    assert signature.host_action == "message.send"
    assert "notify_human" in signature.canonical_tags
    assert signature.side_effect.value == "external_write"


def test_action_gate_blocks_matched_hard_prohibition_and_writes_receipt() -> None:
    store = make_store()
    store.add_contract(push_prohibition())

    result = ActionGate(store).gate(git_push_signature())

    assert result.decision.decision.value == "block"
    assert "Action violates rule MAC-push" in result.decision.reason
    assert result.receipt.contracts_used == ["MAC-push"]
    assert store.list_receipts()[0].decision.value == "block"


def test_action_gate_drops_generic_exec_when_specific_action_is_available() -> None:
    store = make_store()
    store.add_contract(
        Contract(
            id="MAC-web",
            text="For this repo, do not use web search without asking.",
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            strength=Strength.HARD,
            source=source(),
            scope=project_scope(),
            lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
            action_constraints=ActionConstraints(
                host_actions=["exec", "web.search"],
                canonical_tags=["external_write", "network_read"],
            ),
        )
    )
    builder = ActionSignatureBuilder()
    context = SignatureContext(session_id="sess-1", cwd="/workspace/project", repo="project")

    local_test = builder.build(
        tool_name="exec",
        raw_arguments={"cmd": "pytest tests/test_core_flow.py"},
        intent="run local tests",
        context=context,
    )
    web_search = builder.build(
        tool_name="web.search",
        raw_arguments={"query": "package docs"},
        intent="browse package docs",
        context=context,
    )

    assert ActionGate(store).gate(local_test).decision.decision.value == "allow"
    assert ActionGate(store).gate(web_search).decision.decision.value == "block"


def test_excluded_action_bypasses_gate_with_receipt() -> None:
    store = make_store()
    store.add_contract(push_prohibition())
    signature = ActionSignatureBuilder().build(
        tool_name="file.read",
        raw_arguments={"path": "README.md"},
        context=SignatureContext(session_id="sess-1", cwd="/workspace/project", repo="project"),
    )

    result = ActionGate(store, exclude_actions={"file.read"}).gate(signature)

    assert result.decision.decision.value == "allow"
    assert result.receipt.result == "excluded_action"


def test_excluded_action_can_match_tool_name_and_parameter_regex() -> None:
    store = make_store()
    store.add_contract(push_prohibition())
    builder = ActionSignatureBuilder()
    context = SignatureContext(session_id="sess-1", cwd="/workspace/project", repo="project")
    status_signature = builder.build(
        tool_name="exec",
        raw_arguments={"cmd": "git status --short"},
        context=context,
    )
    push_signature = builder.build(
        tool_name="exec",
        raw_arguments={"cmd": "git push origin main"},
        context=context,
    )
    gate = ActionGate(
        store,
        exclude_actions=[
            ExcludedActionPattern(
                tool_name="exec",
                parameter_regex={"cmd": r"^git\s+status(\s|$)"},
            )
        ],
    )

    status_result = gate.gate(status_signature)
    push_result = gate.gate(push_signature)

    assert status_result.receipt.result == "excluded_action"
    assert push_result.decision.decision.value == "block"


def test_file_read_is_not_excluded_by_default() -> None:
    store = make_store()
    store.add_contract(
        Contract(
            id="MAC-read",
            text="Do not read project files.",
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            strength=Strength.HARD,
            source=source(),
            scope=project_scope(),
            lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
            action_constraints=ActionConstraints(host_actions=["file.read"]),
        )
    )
    signature = ActionSignatureBuilder().build(
        tool_name="file.read",
        raw_arguments={"path": "README.md"},
        context=SignatureContext(session_id="sess-1", cwd="/workspace/project", repo="project"),
    )

    result = ActionGate(store).gate(signature)

    assert result.decision.decision.value == "block"
    assert result.receipt.contracts_used == ["MAC-read"]


def test_action_gate_does_not_gate_preferences() -> None:
    store = make_store()
    store.add_contract(
        preference("MAC-pref", "Prefer concise implementation notes.").model_copy(
            update={"action_constraints": ActionConstraints(host_actions=["git.push"])}
        )
    )

    result = ActionGate(store).gate(git_push_signature())

    assert result.decision.decision.value == "allow"
    assert result.receipt.contracts_used == []
    assert result.receipt.contracts_ignored[0].reason == "preference_not_gated"


def test_action_gate_override_edge_allows_blocked_rule() -> None:
    store = make_store()
    store.add_contract(push_prohibition())
    store.add_edge(
        ContractEdge(
            from_contract="OVERRIDE-test",
            to_contract="MAC-push",
            relation=EdgeRelation.OVERRIDE,
            scope=project_scope(),
            lifecycle=Lifecycle(type=LifecycleType.BOUNDED_TASK),
            source=source(SourceKind.AGENT_INFERRED),
        )
    )

    result = ActionGate(store).gate(git_push_signature())

    assert result.decision.decision.value == "allow"
    assert result.receipt.contracts_used == []
    assert result.receipt.contracts_ignored[0].reason == "override_applied"
    assert result.receipt.edges_applied == [store.list_edges()[0].id]


def test_conflict_resolver_supersedes_lower_authority_conflict_with_scoped_edge() -> None:
    store = make_store()
    old = Contract(
        id="MAC-old",
        text="Always push code to Git.",
        kind=ContractKind.REQUIREMENT,
        modality=Modality.MUST,
        strength=Strength.HARD,
        source=source(SourceKind.PROJECT_DOC),
        scope=project_scope(),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        action_constraints=ActionConstraints(host_actions=["git.push"]),
    )
    store.add_contract(old)

    result = ConflictResolver(store).insert(push_prohibition("MAC-new"))

    assert result.relation == EdgeRelation.CONFLICTS_WITH
    assert store.get_contract("MAC-old").status == ContractStatus.SUPERSEDED
    assert result.contract.supersedes == ["MAC-old"]
    assert store.list_edges()[0].scope.workspace == "/workspace/project"


def test_relation_candidate_retrieval_uses_text_bm25_pattern_overlap_and_scope_filter() -> None:
    store = make_store()
    local = push_prohibition_from_source("MAC-local", SourceKind.PROJECT_DOC)
    other_workspace = push_prohibition_from_source(
        "MAC-other",
        SourceKind.PROJECT_DOC,
    ).model_copy(update={"scope": project_scope("/workspace/other")})
    store.add_contract(local)
    store.add_contract(other_workspace)
    resolver = ConflictResolver(store)

    candidates = resolver.find_relation_candidates(
        push_prohibition_from_source(
            "MAC-candidate",
            SourceKind.USER_TURN,
            "Do not run git push until I approve it.",
        )
    )

    assert [item.existing.id for item in candidates] == ["MAC-local"]
    assert candidates[0].similarity >= 0.4
    assert candidates[0].text_score > 0
    assert candidates[0].pattern_score == 1.0


def test_conflict_resolver_uses_llm_relation_decision_before_fallback() -> None:
    prompts: list[str] = []

    def relation_provider(prompt: str) -> str:
        prompts.append(prompt)
        return '{"relations":[{"existing_id":"MAC-existing","relation":"duplicate"}]}'

    store = make_store()
    store.add_contract(push_prohibition_from_source("MAC-existing", SourceKind.PROJECT_DOC))
    candidate = push_prohibition_from_source(
        "MAC-candidate",
        SourceKind.USER_TURN,
        "Do not run git push until I approve it.",
    )

    result = ConflictResolver(store, relation_response_provider=relation_provider).insert(candidate)

    assert result.relation == EdgeRelation.DUPLICATE
    assert store.get_contract("MAC-existing").status == ContractStatus.SUPERSEDED
    assert store.get_contract("MAC-candidate").status == ContractStatus.ACTIVE
    assert "text_score" in prompts[0]
    assert "pattern_score" in prompts[0]
    assert "similarity" in prompts[0]


def test_conflict_resolver_batch_groups_overlapping_retrieval_into_one_llm_call() -> None:
    prompts: list[str] = []

    def relation_provider(prompt: str) -> str:
        prompts.append(prompt)
        return (
            '{"relations":['
            '{"new_id":"MAC-exception","existing_id":"MAC-generated","relation":"exception_to"},'
            '{"new_id":"MAC-core","existing_id":"MAC-generated","relation":"refinement"}'
            "]}"
        )

    store = make_store()
    store.add_contract(
        file_rule(
            "MAC-generated",
            text="Do not edit files under generated/**.",
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            path_glob="generated/**",
            source_kind=SourceKind.PROJECT_DOC,
        )
    )
    exception = file_rule(
        "MAC-exception",
        text="For this task only, you may edit files under generated/sandbox/**.",
        kind=ContractKind.EXCEPTION,
        modality=Modality.MAY,
        path_glob="generated/sandbox/**",
        lifecycle_type=LifecycleType.BOUNDED_TASK,
    )
    refinement = file_rule(
        "MAC-core",
        text="Do not edit files under generated/core/**.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        path_glob="generated/core/**",
    )

    results = ConflictResolver(store, relation_response_provider=relation_provider).insert_batch(
        [exception, refinement]
    )

    assert len(prompts) == 1
    assert "unique_retrieved_rules" in prompts[0]
    assert "overlapped_retrieved_rules" in prompts[0]
    assert "MAC-exception" in prompts[0]
    assert "MAC-core" in prompts[0]
    assert "MAC-generated" in prompts[0]
    assert [result.relation for result in results] == [
        EdgeRelation.EXCEPTION_TO,
        EdgeRelation.REFINEMENT,
    ]
    assert [edge.relation for edge in store.list_edges()] == [
        EdgeRelation.EXCEPTION_TO,
        EdgeRelation.REFINEMENT,
    ]


def test_conflict_resolver_batch_splits_disjoint_components() -> None:
    prompts: list[str] = []

    def relation_provider(prompt: str) -> str:
        prompts.append(prompt)
        if "MAC-docs-new" in prompt:
            return '{"relations":[{"existing_id":"MAC-docs-old","relation":"refinement"}]}'
        return '{"relations":[{"existing_id":"MAC-tests-old","relation":"refinement"}]}'

    store = make_store()
    store.add_contract(
        file_rule(
            "MAC-docs-old",
            text="Use ripgrep when searching documentation under docs/**.",
            kind=ContractKind.REQUIREMENT,
            modality=Modality.MUST,
            path_glob="docs/**",
            source_kind=SourceKind.PROJECT_DOC,
            host_action="file.search",
            tag="search",
        )
    )
    store.add_contract(
        file_rule(
            "MAC-tests-old",
            text="Run pytest before editing test files under tests/**.",
            kind=ContractKind.REQUIREMENT,
            modality=Modality.MUST,
            path_glob="tests/**",
            source_kind=SourceKind.PROJECT_DOC,
            host_action="test.run",
            tag="test",
        )
    )
    docs_new = file_rule(
        "MAC-docs-new",
        text="Use rg for searching docs/** files.",
        kind=ContractKind.REQUIREMENT,
        modality=Modality.MUST,
        path_glob="docs/**",
        host_action="file.search",
        tag="search",
    )
    tests_new = file_rule(
        "MAC-tests-new",
        text="Run pytest before changing tests/** files.",
        kind=ContractKind.REQUIREMENT,
        modality=Modality.MUST,
        path_glob="tests/**",
        host_action="test.run",
        tag="test",
    )

    results = ConflictResolver(
        store,
        relation_response_provider=relation_provider,
        max_relation_workers=2,
    ).insert_batch([docs_new, tests_new])

    assert len(prompts) == 2
    assert [result.relation for result in results] == [
        EdgeRelation.REFINEMENT,
        EdgeRelation.REFINEMENT,
    ]
    assert {edge.to_contract for edge in store.list_edges()} == {
        "MAC-docs-old",
        "MAC-tests-old",
    }


def test_conflict_resolver_falls_back_to_patterns_when_llm_output_is_invalid() -> None:
    store = make_store()
    old = Contract(
        id="MAC-old",
        text="Always push code to Git.",
        kind=ContractKind.REQUIREMENT,
        modality=Modality.MUST,
        strength=Strength.HARD,
        source=source(SourceKind.PROJECT_DOC),
        scope=project_scope(),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        action_constraints=ActionConstraints(host_actions=["git.push"]),
    )
    store.add_contract(old)

    result = ConflictResolver(
        store,
        relation_response_provider=lambda _prompt: "not json",
    ).insert(push_prohibition("MAC-new"))

    assert result.relation == EdgeRelation.CONFLICTS_WITH
    assert store.get_contract("MAC-old").status == ContractStatus.SUPERSEDED


def test_conflict_resolver_runs_explicit_dedup_before_general_relations() -> None:
    store = make_store()
    existing = push_prohibition_from_source("MAC-existing", SourceKind.PROJECT_DOC)
    store.add_contract(existing)
    candidate = push_prohibition_from_source(
        "MAC-candidate",
        SourceKind.USER_TURN,
        "Do not run git push until I approve it.",
    )
    resolver = ConflictResolver(store)

    dedup_candidates = resolver.find_dedup_candidates(candidate)
    result = resolver.insert(candidate)

    assert dedup_candidates
    assert dedup_candidates[0].existing.id == "MAC-existing"
    assert dedup_candidates[0].relation == EdgeRelation.DUPLICATE
    assert result.relation == EdgeRelation.DUPLICATE
    assert store.get_contract("MAC-existing").status == ContractStatus.SUPERSEDED
    assert store.get_contract("MAC-candidate").status == ContractStatus.ACTIVE
    assert store.list_edges()[0].relation == EdgeRelation.DUPLICATE


def test_conflict_resolver_keeps_broader_publish_clause_independent() -> None:
    store = make_store()
    store.add_contract(push_prohibition("MAC-push"))
    broader = Contract(
        id="MAC-publish",
        text="Do not publish anything yet.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=source(),
        scope=project_scope(),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        action_constraints=ActionConstraints(
            host_actions=["git.push"],
            canonical_tags=["external_write", "publish_code"],
        ),
    )

    result = ConflictResolver(store).insert(broader)

    assert result.relation == EdgeRelation.INDEPENDENT
    assert store.get_contract("MAC-push").status == ContractStatus.ACTIVE
    assert store.get_contract("MAC-publish").status == ContractStatus.ACTIVE
    assert store.list_edges() == []


def test_action_gate_reports_specific_approval_boundary_before_broader_publish_rule() -> None:
    store = make_store()
    store.add_contract(
        Contract(
            id="MAC-publish",
            text="Do not publish anything yet.",
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            strength=Strength.HARD,
            source=source(),
            scope=project_scope(),
            lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
            action_constraints=ActionConstraints(
                host_actions=["git.push"],
                canonical_tags=["external_write", "publish_code"],
            ),
        )
    )
    store.add_contract(push_prohibition("MAC-push"))

    result = ActionGate(store).gate(git_push_signature())

    assert result.decision.decision.value == "block"
    assert result.receipt.contracts_used == ["MAC-push"]
    assert "before asking me" in result.decision.reason


def test_conflict_resolver_rejects_lower_authority_duplicate() -> None:
    store = make_store()
    existing = push_prohibition_from_source("MAC-existing", SourceKind.USER_TURN)
    store.add_contract(existing)
    candidate = push_prohibition_from_source(
        "MAC-candidate",
        SourceKind.PROJECT_DOC,
        "Do not run git push until I approve it.",
    )

    result = ConflictResolver(store).insert(candidate)

    assert result.relation == EdgeRelation.DUPLICATE
    assert store.get_contract("MAC-existing").status == ContractStatus.ACTIVE
    assert store.get_contract("MAC-candidate").status == ContractStatus.REJECTED
    assert store.list_edges()[0].relation == EdgeRelation.DUPLICATE


def test_prompt_intake_retrieval_uses_adapter_context_and_path_hints() -> None:
    store = make_store()
    store.add_contract(push_prohibition("MAC-local"))
    store.add_contract(
        push_prohibition("MAC-other").model_copy(update={"scope": project_scope("/workspace/other")})
    )
    store.add_contract(preference("MAC-pref", "Prefer concise implementation notes."))
    context = PromptRetrievalContext(
        session_id="sess-1",
        user_id="user-1",
        workspace="/workspace/project",
        repo="project",
        user_turn="Please update src/app.py and avoid unnecessary git operations.",
    )

    packets = PromptIntakeRetriever(store).retrieve(context)

    assert [packet.id for packet in packets] == ["MAC-pref", "MAC-local"]
    assert packets[0].channel == "preference"
    assert packets[1].channel == "local-reminder"
    assert "target=src/app.py" in packets[1].inclusion_reason


def test_prompt_intake_retrieval_uses_action_hints_without_path_target() -> None:
    store = make_store()
    store.add_contract(
        Contract(
            id="MAC-web",
            text="For this repo, do not use web search without asking.",
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            strength=Strength.HARD,
            source=source(),
            scope=project_scope(),
            lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
            action_constraints=ActionConstraints(
                host_actions=["web.search"],
                canonical_tags=["network_read"],
            ),
        )
    )

    retriever = PromptIntakeRetriever(store)
    packets = retriever.retrieve(
        PromptRetrievalContext(
            session_id="sess-1",
            user_id="user-1",
            workspace="/workspace/project",
            repo="project",
            user_turn="Can you check online for parser docs?",
        )
    )
    rendered = retriever.render_prompt_text(packets)

    assert [packet.id for packet in packets] == ["MAC-web"]
    assert "query-actions=network_read" in packets[0].inclusion_reason
    assert "web search" in rendered


def test_prompt_intake_render_uses_compact_plain_text_budget() -> None:
    store = make_store()
    store.add_contract(preference("MAC-pref", "Prefer concise implementation notes."))
    store.add_contract(
        push_prohibition("MAC-local").model_copy(
            update={"text": "Do not push git changes for files under src/** without approval."}
        )
    )
    retriever = PromptIntakeRetriever(store)
    packets = retriever.retrieve(
        PromptRetrievalContext(
            session_id="sess-1",
            user_id="user-1",
            workspace="/workspace/project",
            repo="project",
            user_turn="Please edit src/app.py.",
        )
    )

    rendered = retriever.render_prompt_text(packets)

    assert "Preferences:" in rendered
    assert "Local reminders:" in rendered
    assert "MAC-pref" in rendered
    assert "MAC-local" in rendered
    assert "{" not in rendered
    assert "}" not in rendered
    assert len(rendered) // 4 <= DEFAULT_PROMPT_TOKEN_BUDGET


def test_ambiguity_monitor_enqueues_and_completes_refinement_job() -> None:
    store = make_store()
    contract = push_prohibition()
    predicate = CompiledPredicateVersion(
        id="PV-current",
        contract_id=contract.id,
        version="PV-001",
        host_action_patterns=[HostActionPattern(action="exec")],
    )
    store.add_contract(contract.model_copy(update={"compiled_predicates": predicate}))
    for index in range(6):
        store.add_predicate_evaluation(
            PredicateEvaluation(
                contract_id=contract.id,
                predicate_version_id=predicate.id,
                signature_id=f"AS-amb-{index}",
                match_outcome=MatchOutcome.AMBIGUOUS,
            )
        )
    for index in range(4):
        store.add_predicate_evaluation(
            PredicateEvaluation(
                contract_id=contract.id,
                predicate_version_id=predicate.id,
                signature_id=f"AS-ok-{index}",
                match_outcome=MatchOutcome.MATCHED,
            )
        )

    monitor = AmbiguityMonitor(store)
    job = monitor.enqueue_if_needed(contract.id, predicate.id)
    completed = monitor.run_next_pending()

    assert job is not None
    assert completed is not None
    assert completed.status.value == "completed"
    assert completed.result_predicate_version_id is not None


def test_action_gate_auto_enqueues_refinement_job_after_ambiguity_window() -> None:
    store = make_store()
    predicate = CompiledPredicateVersion(
        id="PV-current",
        contract_id="MAC-push",
        version="PV-001",
    )
    store.add_contract(
        Contract(
            id="MAC-push",
            text="Do not perform risky release actions without approval.",
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            strength=Strength.HARD,
            source=source(),
            scope=project_scope(),
            lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
            compiled_predicates=predicate,
        )
    )
    gate = ActionGate(store)

    for index in range(10):
        signature = ActionSignatureBuilder().build(
            tool_name="exec",
            raw_arguments={"cmd": f"git push origin branch-{index}"},
            intent="publish branch",
            context=SignatureContext(
                session_id="sess-amb",
                cwd="/workspace/project",
                repo="project",
            ),
        )
        assert gate.gate(signature).decision.decision.value == "block"

    jobs = store.list_refinement_jobs(JobStatus.PENDING.value)
    assert len(jobs) == 1
    assert jobs[0].contract_id == "MAC-push"
    assert jobs[0].predicate_version_id != "PV-current"
    assert len(jobs[0].recent_signature_ids) == 10


def test_llm_predicate_refinement_uses_ambiguous_invocation_results_only_for_patterns() -> None:
    prompts: list[str] = []

    def provider(prompt: str) -> str:
        prompts.append(prompt)
        return (
            '{"host_action_patterns":['
            '{"action":"git.push","tool_name":"exec","parameter_regex":{"cmd":"^git\\\\s+push(\\\\s|$)"}}'
            '],"target_patterns":[],"canonical_tags":["external_write","publish_code"]}'
        )

    store = make_store()
    predicate = CompiledPredicateVersion(
        id="PV-current",
        contract_id="MAC-push",
        version="PV-001",
    )
    store.add_contract(
        Contract(
            id="MAC-push",
            text="Do not perform risky release actions without approval.",
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            strength=Strength.HARD,
            source=source(),
            scope=project_scope(),
            lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
            compiled_predicates=predicate,
        )
    )
    gate = ActionGate(store)
    for index in range(10):
        signature = ActionSignatureBuilder().build(
            tool_name="exec",
            raw_arguments={"cmd": f"git push origin branch-{index}"},
            intent="publish branch",
            context=SignatureContext(
                session_id="sess-amb",
                cwd="/workspace/project",
                repo="project",
            ),
        )
        assert gate.gate(signature).decision.decision.value == "block"

    monitor = AmbiguityMonitor(store)
    job = store.list_refinement_jobs(JobStatus.PENDING.value)[0]
    completed = monitor.run_next_pending(LLMPredicateRefiner(provider))

    assert job is not None
    assert completed is not None
    assert completed.status.value == "completed"
    assert prompts
    assert prompts[0].count("git push origin branch-") == 10
    assert "Do not perform risky release actions without approval." in prompts[0]
    assert "host_action_patterns" in prompts[0]
    refined = store.list_predicate_versions("MAC-push")[-1]
    assert refined.refines == job.predicate_version_id
    assert refined.host_action_patterns[0].action == "git.push"
    assert refined.host_action_patterns[0].tool_name == "exec"
    assert refined.host_action_patterns[0].parameter_regex["cmd"].startswith("^git")
    versions = {item.id: item for item in store.list_predicate_versions("MAC-push")}
    assert refined.scope_predicate == versions[job.predicate_version_id].scope_predicate
    stored_contract = store.get_contract("MAC-push")
    assert stored_contract.text == "Do not perform risky release actions without approval."
    assert stored_contract.compiled_predicates.id == refined.id
    assert versions[job.predicate_version_id].status == PredicateStatus.SUPERSEDED
    assert versions[refined.id].status == PredicateStatus.ACTIVE
