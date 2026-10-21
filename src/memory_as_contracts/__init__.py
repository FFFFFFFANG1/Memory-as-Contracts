"""Memory-as-Contracts core package."""

from memory_as_contracts.action_log import (
    ActionLogSearchSpecV1,
    ActionLogSearchTranslator,
    ActionLogView,
)
from memory_as_contracts.adapters import (
    AdapterCapabilities,
    AdapterContext,
    ChangedSource,
    MemorySourceSpec,
)
from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.extractor import (
    HeuristicContractExtractor,
    JsonContractExtractor,
    LLMCallError,
    PolicyIRContractExtractor,
)
from memory_as_contracts.gate import ActionGate, ExcludedActionPattern
from memory_as_contracts.logging_config import configure_logging
from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionOutcome,
    ActionSignature,
    ArgPattern,
    AvailableAction,
    AskRequest,
    AskRequestStatus,
    Contract,
    ContractEdge,
    ContractSource,
    GateDecision,
    Rule,
    RuleAuthority,
    RuleEffect,
    RulePatternVersion,
    RuleSemantics,
    RuleValidity,
    Lifecycle,
    Receipt,
    Scope,
    SourceSnapshot,
    ToolPattern,
    ValidatorEnforcementShape,
    ValidatorInstallationRecord,
    ValidatorInstallationStatus,
    ValidatorRuntimeErrorRecord,
    ValidatorState,
    ValidatorStateTransition,
    ValidatorVerdict,
    ValidatorVersion,
)
from memory_as_contracts.normalizers import LifecycleNormalizer, ScopeNormalizer
from memory_as_contracts.pattern_validation import (
    PATTERN_REFINEMENT_SYSTEM_PROMPT,
    PatternProvisioner,
    PatternProvisioningResult,
    PatternValidationIssue,
    PatternVerificationResult,
    PatternVerifier,
)
from memory_as_contracts.policy_ir import PolicyIR, PolicyIREvaluator
from memory_as_contracts.resolver import ConflictResolver
from memory_as_contracts.retrieval import PromptIntakeRetriever, PromptRetrievalContext
from memory_as_contracts.signatures import ActionSignatureBuilder
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule

__all__ = [
    "ActionGate",
    "ActionLogEntryV1",
    "ActionLogSearchSpecV1",
    "ActionLogSearchTranslator",
    "ActionLogView",
    "ActionOutcome",
    "ActionSignature",
    "ActionSignatureBuilder",
    "AdapterContext",
    "AdapterCapabilities",
    "ArgPattern",
    "AvailableAction",
    "AskRequest",
    "AskRequestStatus",
    "ChangedSource",
    "ClaudeCodeAdapter",
    "Contract",
    "ContractEdge",
    "ContractSource",
    "ContractStore",
    "ConflictResolver",
    "configure_logging",
    "CodexAdapter",
    "ExcludedActionPattern",
    "GateDecision",
    "HeuristicContractExtractor",
    "JsonContractExtractor",
    "Lifecycle",
    "LifecycleNormalizer",
    "LLMCallError",
    "MemorySourceSpec",
    "NanobotAdapter",
    "OpenClawAdapter",
    "PolicyCompiler",
    "PolicyIRContractExtractor",
    "PolicyIR",
    "PolicyIREvaluator",
    "PromptIntakeRetriever",
    "PromptRetrievalContext",
    "Receipt",
    "Rule",
    "RuleAuthority",
    "RuleEffect",
    "RulePatternVersion",
    "RuleSemantics",
    "RuleValidity",
    "Scope",
    "ScopeNormalizer",
    "SourceSnapshot",
    "PATTERN_REFINEMENT_SYSTEM_PROMPT",
    "PatternProvisioner",
    "PatternProvisioningResult",
    "PatternValidationIssue",
    "PatternVerificationResult",
    "PatternVerifier",
    "ToolCapabilityCapsule",
    "ToolPattern",
    "ValidatorEnforcementShape",
    "ValidatorInstallationRecord",
    "ValidatorInstallationStatus",
    "ValidatorRuntimeErrorRecord",
    "ValidatorState",
    "ValidatorStateTransition",
    "ValidatorVerdict",
    "ValidatorVersion",
]

__version__ = "0.1.0"


def __getattr__(name: str):
    if name == "ClaudeCodeAdapter":
        from memory_as_contracts.adapters.claude_code import ClaudeCodeAdapter

        return ClaudeCodeAdapter
    if name == "CodexAdapter":
        from memory_as_contracts.adapters.codex import CodexAdapter

        return CodexAdapter
    if name == "NanobotAdapter":
        from memory_as_contracts.adapters.nanobot import NanobotAdapter

        return NanobotAdapter
    if name == "OpenClawAdapter":
        from memory_as_contracts.adapters.openclaw import OpenClawAdapter

        return OpenClawAdapter
    raise AttributeError(name)
