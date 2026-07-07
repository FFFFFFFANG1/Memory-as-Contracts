"""OpenClaw memory tool executor for the MAC benchmark agent loop.

Intercepts memory_search and memory_get tool calls and routes them to the
per-task OpenClawMemoryState, while passing all other calls through to the
inner executor.
"""

from __future__ import annotations

from typing import Any

from bench.MAC.agent.loop.tools import HeuristicToolExecutor, ToolExecution, parse_tool_arguments
from bench.MAC.agent.memory.openclaw import OpenClawMemoryProvider, OpenClawMemoryState


class OpenClawToolExecutor:
    """Wraps an inner executor and handles memory_search / memory_get locally."""

    def __init__(
        self,
        *,
        state: OpenClawMemoryState,
        provider: OpenClawMemoryProvider,
        request: Any,
        inner: Any | None = None,
        agent: str = "",
    ) -> None:
        self.state = state
        self.provider = provider
        self.request = request
        self.inner = inner or HeuristicToolExecutor(agent=agent)

    def execute(self, *, call_id: str, name: str, arguments: Any) -> ToolExecution:
        parsed = parse_tool_arguments(arguments)

        if name == "memory_search":
            return self._handle_memory_search(call_id, parsed)
        if name == "memory_get":
            return self._handle_memory_get(call_id, parsed)

        return self.inner.execute(call_id=call_id, name=name, arguments=arguments)

    def _handle_memory_search(self, call_id: str, arguments: dict[str, Any]) -> ToolExecution:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            result = {"results": [], "error": "query parameter is required and must be a string"}
            return ToolExecution(name="memory_search", call_id=call_id, arguments=arguments, result=result)

        max_results_raw = arguments.get("maxResults")
        max_results = int(max_results_raw) if isinstance(max_results_raw, (int, float)) and max_results_raw > 0 else None

        min_score_raw = arguments.get("minScore")
        min_score = float(min_score_raw) if isinstance(min_score_raw, (int, float)) else None

        results = self.provider.hybrid_search(
            self.state,
            query.strip(),
            self.request,
            max_results=max_results,
            min_score=min_score,
        )
        result = {
            "results": results,
            "total": len(results),
            "query": query.strip(),
        }
        return ToolExecution(name="memory_search", call_id=call_id, arguments=arguments, result=result)

    def _handle_memory_get(self, call_id: str, arguments: dict[str, Any]) -> ToolExecution:
        rel_path = arguments.get("path")
        if not isinstance(rel_path, str) or not rel_path.strip():
            result = {"path": "", "text": "", "disabled": True, "error": "path parameter is required"}
            return ToolExecution(name="memory_get", call_id=call_id, arguments=arguments, result=result)

        from_line_raw = arguments.get("from")
        lines_raw = arguments.get("lines")
        from_line = int(from_line_raw) if isinstance(from_line_raw, (int, float)) and from_line_raw > 0 else None
        lines = int(lines_raw) if isinstance(lines_raw, (int, float)) and lines_raw > 0 else None

        result = self.provider.memory_get(
            self.state,
            rel_path.strip(),
            from_line=from_line,
            lines=lines,
        )
        return ToolExecution(name="memory_get", call_id=call_id, arguments=arguments, result=result)
