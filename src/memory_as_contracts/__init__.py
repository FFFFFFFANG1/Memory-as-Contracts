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
    AvailableAction,
    CompiledPredicateVersion,
    Contract,
    ContractEdge,
    ContractSource,
    GateDecision,
    PredicateEvaluation,
    Lifecycle,
    RefinementJob,
    Receipt,
    Scope,
    SourceSnapshot,
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
    "Scope",
    "ScopeNormalizer",
    "SourceSnapshot",
    "ToolCapabilityCapsule",
]

__version__ = "0.1.0"
