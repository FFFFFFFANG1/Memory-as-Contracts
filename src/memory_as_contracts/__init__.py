"""Memory-as-Contracts core package."""

from memory_as_contracts.ambiguity import AmbiguityMonitor, LLMPredicateRefiner
from memory_as_contracts.adapters import (
    AdapterContext,
    ChangedSource,
    ClaudeCodeAdapter,
    CodexAdapter,
    MemorySourceSpec,
    NanobotAdapter,
    OpenClawAdapter,
)
from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.extractor import HeuristicContractExtractor, JsonContractExtractor
from memory_as_contracts.gate import ActionGate, ExcludedActionPattern
from memory_as_contracts.models import (
    ActionConstraints,
    ActionSignature,
    AmbiguityEvent,
    ArgPattern,
    AvailableAction,
    CompiledPredicateVersion,
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
    PredicateEvaluation,
    Lifecycle,
    RefinementJob,
    Receipt,
    Scope,
    SourceSnapshot,
    TargetPattern,
    ToolPattern,
)
from memory_as_contracts.normalizers import LifecycleNormalizer, ScopeNormalizer
from memory_as_contracts.resolver import ConflictResolver
from memory_as_contracts.retrieval import PromptIntakeRetriever, PromptRetrievalContext
from memory_as_contracts.signatures import ActionSignatureBuilder
from memory_as_contracts.store import ContractStore
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule

__all__ = [
    "ActionConstraints",
    "ActionGate",
    "ActionSignature",
    "ActionSignatureBuilder",
    "AdapterContext",
    "AmbiguityEvent",
    "AmbiguityMonitor",
    "ArgPattern",
    "AvailableAction",
    "ChangedSource",
    "ClaudeCodeAdapter",
    "CompiledPredicateVersion",
    "Contract",
    "ContractEdge",
    "ContractSource",
    "ContractStore",
    "ConflictResolver",
    "CodexAdapter",
    "ExcludedActionPattern",
    "GateDecision",
    "HeuristicContractExtractor",
    "JsonContractExtractor",
    "PredicateEvaluation",
    "Lifecycle",
    "LifecycleNormalizer",
    "LLMPredicateRefiner",
    "MemorySourceSpec",
    "NanobotAdapter",
    "OpenClawAdapter",
    "PolicyCompiler",
    "PromptIntakeRetriever",
    "PromptRetrievalContext",
    "RefinementJob",
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
    "TargetPattern",
    "ToolCapabilityCapsule",
    "ToolPattern",
]

__version__ = "0.1.0"
