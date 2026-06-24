"""LLM-backed virtual tool execution for the benchmark agent loop."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from bench.MAC.agent.loop.tools import (
    HeuristicToolExecutor,
    ToolExecution,
    ToolRoute,
    hash_json,
    parse_tool_arguments,
    route_tool,
    stable_json,
    tool_by_name,
)


class ToolReturnModelClient(Protocol):
    async def __call__(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        """Return a chat response whose content is a JSON tool result payload."""


@dataclass(slots=True)
class LLMToolReturnConfig:
    mode: str = "hybrid"
    max_attempts: int = 3
    max_payload_chars: int = 12000
    history_limit: int = 12


@dataclass(slots=True)
class VirtualState:
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    exposed_ports: list[Any] = field(default_factory=list)
    deployments: list[Any] = field(default_factory=list)
    mutations: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "files": self.files,
            "dependencies": self.dependencies[-20:],
            "projects": self.projects[-10:],
            "exposed_ports": self.exposed_ports[-10:],
            "deployments": self.deployments[-10:],
            "recent_mutations": self.mutations[-20:],
        }

    def hash(self) -> str:
        return hash_json(self.summary())

    def record(self, tool_name: str, arguments: dict[str, Any], result: Any) -> None:
        path = _first_text_argument(
            arguments,
            ("path", "file_path", "target_file", "target", "filename", "relative_workspace_path"),
        )
        normalized = tool_name.lower()
        mutation = {
            "tool": tool_name,
            "arguments": _truncate_for_context(arguments, 1200),
            "result": _truncate_for_context(result, 1200),
        }
        if any(token in normalized for token in ("write", "edit", "patch", "replace")):
            if path:
                self.files[path] = {
                    "last_operation": tool_name,
                    "known_content_from_arguments": arguments.get("content"),
                    "last_arguments": _truncate_for_context(arguments, 1200),
                }
            self.mutations.append(mutation)
        elif any(token in normalized for token in ("delete", "rename")):
            if path:
                self.files[path] = {
                    "last_operation": tool_name,
                    "last_arguments": _truncate_for_context(arguments, 1200),
                }
            self.mutations.append(mutation)
        elif "dependency" in normalized:
            dependency = _first_text_argument(arguments, ("dependency", "package", "name"))
            if dependency:
                self.dependencies.append(dependency)
            self.mutations.append(mutation)
        elif "create_project" == normalized:
            project = _first_text_argument(arguments, ("name", "project", "path"))
            if project:
                self.projects.append(project)
            self.mutations.append(mutation)
        elif normalized == "expose_port":
            self.exposed_ports.append(_truncate_for_context(result, 1200))
            self.mutations.append(mutation)
        elif "deploy" in normalized:
            self.deployments.append(_truncate_for_context(result, 1200))
            self.mutations.append(mutation)


class DryRunToolReturnModelClient:
    """Small deterministic tool-return model for dry runs and tests."""

    async def __call__(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = messages[-1].get("content", "") if messages else ""
        tool_name = "tool"
        match = re.search(r'"tool_name"\s*:\s*"([^"]+)"', prompt)
        if match:
            tool_name = match.group(1)
        return {
            "content": json.dumps(
                {
                    "summary": f"Dry-run simulated outcome for {tool_name}.",
                },
                ensure_ascii=False,
            ),
            "tool_calls": [],
        }


class LLMToolExecutor:
    """Route deterministic tools locally and synthesize content-bearing tool returns with an LLM."""

    def __init__(
        self,
        *,
        agent: str,
        tools: list[dict[str, Any]],
        task_uid: str,
        user_prompt: str,
        memory: str,
        model_client: ToolReturnModelClient,
        config: LLMToolReturnConfig | None = None,
        heuristic_executor: HeuristicToolExecutor | None = None,
    ) -> None:
        self.agent = agent
        self.tools = tools
        self.task_uid = task_uid
        self.user_prompt = user_prompt
        self.memory = memory
        self.model_client = model_client
        self.config = config or LLMToolReturnConfig()
        self.heuristic_executor = heuristic_executor or HeuristicToolExecutor(agent=agent)
        self.cache: dict[str, Any] = {}
        self.state = VirtualState()
        self.history: list[dict[str, Any]] = []

    async def execute(self, *, call_id: str, name: str, arguments: Any) -> ToolExecution:
        parsed = parse_tool_arguments(arguments)
        route = self._route(name=name, arguments=parsed)
        if self.config.mode == "heuristic" or route == "heuristic":
            return self._execute_heuristic(call_id=call_id, name=name, arguments=parsed, route=route)
        if self.config.mode == "llm" or self.config.mode == "hybrid":
            return await self._execute_llm(call_id=call_id, name=name, arguments=parsed)
        return self._execute_heuristic(call_id=call_id, name=name, arguments=parsed, route=route)

    def _route(self, *, name: str, arguments: dict[str, Any]) -> ToolRoute:
        if arguments.get("requires_approval") is True or arguments.get("require_user_approval") is True:
            return "heuristic"
        return route_tool(agent=self.agent, tool_name=name, tool_schema=tool_by_name(self.tools, name))

    def _execute_heuristic(
        self,
        *,
        call_id: str,
        name: str,
        arguments: dict[str, Any],
        route: ToolRoute,
    ) -> ToolExecution:
        execution = self.heuristic_executor.execute(call_id=call_id, name=name, arguments=arguments)
        envelope = self._envelope(
            ok=True,
            source="heuristic",
            route=route,
            result=execution.result,
            attempt=0,
            cached=False,
        )
        self._record_history(name=name, arguments=arguments, envelope=envelope)
        self.state.record(name, arguments, execution.result)
        return ToolExecution(name=name, call_id=call_id, arguments=arguments, result=envelope)

    async def _execute_llm(
        self,
        *,
        call_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolExecution:
        cache_key = self._cache_key(name=name, arguments=arguments)
        if cache_key in self.cache:
            result = copy.deepcopy(self.cache[cache_key])
            envelope = self._envelope(
                ok=True,
                source="llm_tool_return",
                route="llm",
                result=result,
                attempt=0,
                cached=True,
            )
            self._record_history(name=name, arguments=arguments, envelope=envelope)
            return ToolExecution(name=name, call_id=call_id, arguments=arguments, result=envelope)

        last_error = ""
        for attempt in range(1, max(1, self.config.max_attempts) + 1):
            try:
                result = await self._call_tool_return_model(
                    tool_name=name,
                    arguments=arguments,
                    attempt=attempt,
                    last_error=last_error,
                )
                truncated = False
                if len(stable_json(result)) > self.config.max_payload_chars:
                    result = _truncate_for_context(result, self.config.max_payload_chars)
                    truncated = True
                self.cache[cache_key] = copy.deepcopy(result)
                envelope = self._envelope(
                    ok=True,
                    source="llm_tool_return",
                    route="llm",
                    result=result,
                    attempt=attempt,
                    cached=False,
                    truncated_by_runtime=truncated,
                )
                self._record_history(name=name, arguments=arguments, envelope=envelope)
                self.state.record(name, arguments, result)
                return ToolExecution(name=name, call_id=call_id, arguments=arguments, result=envelope)
            except Exception as exc:  # noqa: BLE001 - retry and report controlled failures.
                last_error = f"{type(exc).__name__}: {exc}"

        result = {
            "message": "The benchmark runtime could not synthesize a valid tool result.",
            "tool_name": name,
        }
        envelope = self._envelope(
            ok=False,
            source="llm_tool_return",
            route="llm",
            result=result,
            attempt=max(1, self.config.max_attempts),
            cached=False,
            error="tool_return_generation_failed",
            error_detail=last_error,
        )
        self._record_history(name=name, arguments=arguments, envelope=envelope)
        return ToolExecution(name=name, call_id=call_id, arguments=arguments, result=envelope)

    async def _call_tool_return_model(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        attempt: int,
        last_error: str,
    ) -> dict[str, Any]:
        prompt = self._build_prompt(
            tool_name=tool_name,
            arguments=arguments,
            attempt=attempt,
            last_error=last_error,
        )
        response = await self.model_client(
            messages=[
                {"role": "system", "content": TOOL_RETURN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=[],
        )
        content = _response_content(response)
        result = _parse_json_object(content)
        if not isinstance(result, dict):
            raise ValueError("tool-return LLM must return a JSON object")
        return result

    def _build_prompt(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        attempt: int,
        last_error: str,
    ) -> str:
        payload = {
            "task_uid": self.task_uid,
            "agent": self.agent,
            "attempt": attempt,
            "last_validation_error": last_error,
            "return_schema": result_schema_for_tool(tool_name),
            "output_rules": {
                "return_only_json_object": True,
                "generate_only_result_payload": True,
                "do_not_include_runtime_metadata": [
                    "ok",
                    "simulated",
                    "source",
                    "attempt",
                    "cached",
                    "error",
                    "truncated_by_runtime",
                ],
                "max_payload_chars": self.config.max_payload_chars,
                "minimal_outcome": (
                    "Return the smallest useful simulated outcome for the current tool call. "
                    "For reads, include only the requested file/snippet. For search/list, include a small top-k. "
                    "For shell/test commands, include concise stdout/stderr and short failure snippets only."
                ),
            },
            "current_user_turn": self.user_prompt,
            "memory_project_phase_context": self.memory,
            "tool_schema": tool_by_name(self.tools, tool_name),
            "prior_tool_calls_and_outcomes": self.history[-self.config.history_limit :],
            "virtual_state_summary": self.state.summary(),
            "current_tool_call": {
                "tool_name": tool_name,
                "arguments": arguments,
            },
        }
        return (
            "Generate the simulated result payload for CURRENT_TOOL_CALL only.\n"
            "Do not solve the final user task. Do not call tools. Do not mention this is generated by an LLM.\n"
            "Return only valid JSON matching return_schema.\n\n"
            + json.dumps(payload, indent=2, ensure_ascii=False)
            + "\n\nCURRENT_TOOL_CALL is the last object above. Generate its minimal simulated outcome now."
        )

    def _cache_key(self, *, name: str, arguments: dict[str, Any]) -> str:
        return hash_json(
            {
                "task_uid": self.task_uid,
                "tool_name": name,
                "arguments": arguments,
                "virtual_state_hash": self.state.hash(),
            }
        )

    def _record_history(self, *, name: str, arguments: dict[str, Any], envelope: dict[str, Any]) -> None:
        self.history.append(
            {
                "tool_name": name,
                "arguments": _truncate_for_context(arguments, 1600),
                "outcome": _truncate_for_context(envelope, 2400),
            }
        )

    @staticmethod
    def _envelope(
        *,
        ok: bool,
        source: str,
        route: ToolRoute,
        result: Any,
        attempt: int,
        cached: bool,
        truncated_by_runtime: bool = False,
        error: str | None = None,
        error_detail: str | None = None,
    ) -> dict[str, Any]:
        envelope: dict[str, Any] = {
            "ok": ok,
            "simulated": True,
            "source": source,
            "route": route,
            "attempt": attempt,
            "cached": cached,
            "result": result,
        }
        if truncated_by_runtime:
            envelope["truncated_by_runtime"] = True
        if error:
            envelope["error"] = error
        if error_detail:
            envelope["error_detail"] = error_detail
        return envelope


TOOL_RETURN_SYSTEM_PROMPT = """You are a deterministic virtual benchmark runtime.

Generate the JSON result payload for exactly one current tool call. The caller will add runtime metadata such as ok, simulated, source, attempt, cached, and errors. You must not include those metadata keys.

Be concise and consistent with prior tool outcomes and virtual state. Generate the minimal useful simulated outcome needed for the current tool call only.
""".strip()


def result_schema_for_tool(tool_name: str) -> dict[str, Any]:
    name = tool_name.lower()
    if any(token in name for token in ("shell", "command", "execute")):
        return {
            "type": "object",
            "required": ["exit_code", "stdout", "stderr"],
            "properties": {
                "exit_code": {"type": "integer"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
            },
        }
    if name in {"read_file", "access_mcp_resource", "load_mcp_documentation"}:
        return {
            "type": "object",
            "required": ["path", "content", "truncated"],
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "truncated": {"type": "boolean"},
            },
        }
    if name == "read_files":
        return {
            "type": "object",
            "required": ["files"],
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["path", "content", "truncated"],
                    },
                }
            },
        }
    if any(token in name for token in ("search", "grep", "regex", "definition")):
        return {
            "type": "object",
            "required": ["query", "results"],
            "properties": {
                "query": {"type": "string"},
                "results": {"type": "array", "items": {"type": "object"}},
            },
        }
    if "list" in name or "directory" in name or "dir" in name:
        return {
            "type": "object",
            "required": ["path", "entries"],
            "properties": {
                "path": {"type": "string"},
                "entries": {"type": "array", "items": {"type": "object"}},
            },
        }
    if any(token in name for token in ("browser", "web", "scrape")):
        return {
            "type": "object",
            "required": ["title", "summary"],
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "content": {"type": "string"},
            },
        }
    if "console" in name:
        return {
            "type": "object",
            "required": ["logs", "errors"],
            "properties": {
                "logs": {"type": "array", "items": {"type": "string"}},
                "errors": {"type": "array", "items": {"type": "string"}},
            },
        }
    if "diff" in name:
        return {
            "type": "object",
            "required": ["diffs"],
            "properties": {"diffs": {"type": "array", "items": {"type": "object"}}},
        }
    return {
        "type": "object",
        "required": ["summary"],
        "properties": {"summary": {"type": "string"}},
    }


def _response_content(response: Any) -> str:
    if isinstance(response, dict):
        value = response.get("content", "")
    else:
        value = getattr(response, "content", "")
    return value if isinstance(value, str) else ""


def _parse_json_object(content: str) -> Any:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return json.loads(stripped)


def _first_text_argument(arguments: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _truncate_for_context(value: Any, max_chars: int) -> Any:
    if max_chars <= 0:
        return value
    text = stable_json(value)
    if len(text) <= max_chars:
        return value
    if isinstance(value, str):
        return value[: max(0, max_chars - 24)] + "\n...[truncated]..."
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        budget = max_chars
        for key, item in value.items():
            if budget <= 0:
                result["__truncated__"] = True
                break
            truncated = _truncate_for_context(item, max(100, budget // 2))
            result[key] = truncated
            budget -= len(stable_json({key: truncated}))
        return result
    if isinstance(value, list):
        result_list = []
        budget = max_chars
        for item in value:
            if budget <= 0:
                result_list.append({"__truncated__": True})
                break
            truncated = _truncate_for_context(item, max(100, budget // 2))
            result_list.append(truncated)
            budget -= len(stable_json(truncated))
        return result_list
    return value
