from __future__ import annotations

from datetime import datetime, timezone

from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.gate import ActionGate
from memory_as_contracts.models import (
    ArgPattern,
    Contract,
    ContractKind,
    ContractSource,
    ContractStatus,
    Lifecycle,
    LifecycleType,
    MatchOutcome,
    Modality,
    RuleSemantics,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
    ToolPattern,
)
from memory_as_contracts.pattern_validation import (
    PatternInstaller,
    PatternProvisioner,
    PatternVerifier,
)
from memory_as_contracts.signatures import ActionSignatureBuilder, SignatureContext
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule, object_schema


def _contract(*, check_patterns: list[ToolPattern]) -> Contract:
    return Contract(
        id="MAC-pattern",
        text="Do not push code.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=ContractSource(
            kind=SourceKind.USER_TURN,
            created_at=datetime(2026, 6, 7, tzinfo=timezone.utc),
        ),
        scope=Scope(level=ScopeLevel.PROJECT, workspace="/workspace/project", project="project"),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        semantics=RuleSemantics(actions=["git.push"]),
        check_patterns=check_patterns,
    )


def _bash_capsule() -> ToolCapabilityCapsule:
    return ToolCapabilityCapsule(
        name="Bash",
        description="Runs a shell command.",
        input_schema=object_schema(
            required=("command",),
            properties={
                "command": {"type": "string"},
                "timeout": {"type": "integer"},
            },
        ),
    )


def test_rule_schema_has_no_declarative_targets() -> None:
    rule = _contract(
        check_patterns=[
            ToolPattern(
                tool="Bash",
                args={"command": ArgPattern(regex=r"^git\s+push(?:\s|$)")},
            )
        ]
    )

    assert "targets" not in rule.model_dump(mode="json")


def test_pattern_verifier_checks_tool_schema_and_regex() -> None:
    verifier = PatternVerifier([_bash_capsule()])

    accepted = verifier.verify(
        _contract(
            check_patterns=[
                ToolPattern(
                    tool="Bash",
                    args={"command": ArgPattern(regex=r"^git\s+push(?:\s|$)")},
                )
            ]
        )
    )
    rejected = verifier.verify(
        _contract(
            check_patterns=[
                ToolPattern(
                    tool="Bash",
                    args={"cmd": ArgPattern(regex="(")},
                ),
                ToolPattern(tool="UnknownTool"),
            ]
        )
    )

    assert accepted.accepted is True
    assert rejected.accepted is False
    assert {issue.code for issue in rejected.issues} == {
        "invalid_regex",
        "unknown_argument",
        "unknown_tool",
    }


def test_pattern_provisioner_refines_at_most_once() -> None:
    calls: list[str] = []

    def provider(prompt: str) -> str:
        calls.append(prompt)
        return (
            '{"check_patterns":[{"tool":"Bash","args":{"command":'
            '{"regex":"^git\\\\s+push(?:\\\\s|$)"}}}],'
            '"update_patterns":[]}'
        )

    result = PatternProvisioner(
        verifier=PatternVerifier([_bash_capsule()]),
        response_provider=provider,
    ).provision(
        _contract(
            check_patterns=[
                ToolPattern(tool="Bash", args={"cmd": ArgPattern(regex="(")})
            ]
        )
    )

    assert result.verification.accepted is True
    assert result.refined is True
    assert result.contract.status == ContractStatus.ACTIVE
    assert result.contract.check_patterns[0].args["command"].regex
    assert len(calls) == 1
    assert "invalid_regex" in calls[0]
    assert "unknown_argument" in calls[0]


def test_pattern_provisioner_keeps_invalid_rule_non_hookable_after_one_refine() -> None:
    calls = 0

    def provider(_prompt: str) -> str:
        nonlocal calls
        calls += 1
        return (
            '{"check_patterns":[{"tool":"Bash","args":{"missing":'
            '{"regex":"("}}}],"update_patterns":[]}'
        )

    result = PatternProvisioner(
        verifier=PatternVerifier([_bash_capsule()]),
        response_provider=provider,
    ).provision(
        _contract(check_patterns=[ToolPattern(tool="UnknownTool")])
    )

    assert result.verification.accepted is False
    assert result.contract.status == ContractStatus.CANDIDATE
    assert calls == 1


def test_pattern_matching_has_only_matched_and_not_matched() -> None:
    compiler = PolicyCompiler()
    predicate = compiler.compile(
        _contract(
            check_patterns=[
                ToolPattern(
                    tool="Bash",
                    args={"command": ArgPattern(regex=r"^git\s+push(?:\s|$)")},
                )
            ]
        )
    )
    signature = ActionSignatureBuilder().build(
        tool_name="Bash",
        raw_arguments={},
        context=SignatureContext(
            host="claude_code",
            agent_family="claude_code",
            session_id="sess-1",
            cwd="/workspace/project",
            repo="project",
        ),
    )

    assert compiler.evaluate(predicate, signature) == MatchOutcome.NOT_MATCHED
    assert {outcome.value for outcome in MatchOutcome} == {"matched", "not_matched"}


def test_gate_does_not_materialize_unverified_contract_patterns() -> None:
    store = ContractStore(":memory:")
    store.init_db()
    store.add_contract(
        _contract(
            check_patterns=[
                ToolPattern(
                    tool="Bash",
                    args={"command": ArgPattern(regex=r"^git\s+push(?:\s|$)")},
                )
            ]
        )
    )
    signature = ActionSignatureBuilder().build(
        tool_name="Bash",
        raw_arguments={"command": "git push origin main"},
        context=SignatureContext(
            host="claude_code",
            agent_family="claude_code",
            session_id="sess-1",
            cwd="/workspace/project",
            repo="project",
        ),
    )

    result = ActionGate(store).gate(signature)

    assert result.decision.decision.value == "allow"
    assert store.list_rule_pattern_versions("MAC-pattern") == []


def test_pattern_installer_is_the_only_verify_compile_store_path() -> None:
    store = ContractStore(":memory:")
    store.init_db()
    contract = _contract(
        check_patterns=[
            ToolPattern(
                tool="Bash",
                args={"command": ArgPattern(regex=r"^git\s+push(?:\s|$)")},
            )
        ]
    )
    installed = PatternInstaller(
        store=store,
        verifier=PatternVerifier([_bash_capsule()]),
    ).install(contract)
    signature = ActionSignatureBuilder().build(
        tool_name="Bash",
        raw_arguments={"command": "git push origin main"},
        context=SignatureContext(
            host="claude_code",
            agent_family="claude_code",
            session_id="sess-1",
            cwd="/workspace/project",
            repo="project",
        ),
    )

    result = ActionGate(store).gate(signature)

    assert installed.verification.accepted is True
    assert installed.pattern_version is not None
    assert store.get_active_rule_pattern_version(contract.id) == installed.pattern_version
    assert result.decision.decision.value == "reject"
