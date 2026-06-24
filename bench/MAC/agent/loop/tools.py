"""Heuristic tool execution for the benchmark agent loop."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from bench.MAC.agent.loop.prompt import REPO_ROOT, load_json, slugify_agent

DEFAULT_AGENT_ROOT = REPO_ROOT / "bench" / "MAC" / "agent"
ToolRoute = Literal["heuristic", "llm"]

LLM_TOOLS_BY_AGENT: dict[str, set[str]] = {
    "Cline_Prompt": {
        "execute_command",
        "read_file",
        "search_files",
        "list_files",
        "list_code_definition_names",
        "browser_action",
        "use_mcp_tool",
        "access_mcp_resource",
        "load_mcp_documentation",
    },
    "Codex CLI_Prompt": {"run_shell_command"},
    "Cursor Prompts_cursor agent": {
        "codebase_search",
        "read_file",
        "run_shell_command",
        "list_directory",
        "regex_search",
        "file_search",
        "web_search",
        "diff_history",
    },
    "Cursor Prompts_cursor chat": {
        "codebase_search",
        "read_file",
        "list_dir",
        "grep_search",
        "file_search",
        "web_search",
    },
    "Lovable_Lovable Prompt": {"read_console_logs"},
    "Manus Agent Tools & Prompt_Agent loop": {"shell_command", "read_file", "browser_control"},
    "Same.dev_Prompt": {
        "web_search",
        "web_scrape",
        "run_shell_command",
        "list_directory",
        "file_search",
        "grep_search",
        "read_files",
    },
}

HEURISTIC_TOOLS_BY_AGENT: dict[str, set[str]] = {
    "Cline_Prompt": {"write_to_file", "replace_in_file", "send_message"},
    "Codex CLI_Prompt": {"apply_patch", "insert_patch", "send_message"},
    "Cursor Prompts_cursor agent": {"edit_file", "delete_file", "reapply_edit", "send_message"},
    "Cursor Prompts_cursor chat": {"send_message"},
    "Lovable_Lovable Prompt": {
        "write_file",
        "rename_file",
        "delete_file",
        "add_dependency",
        "send_message",
    },
    "Manus Agent Tools & Prompt_Agent loop": {
        "write_file",
        "edit_file",
        "expose_port",
        "send_message",
    },
    "Same.dev_Prompt": {
        "create_project",
        "edit_file",
        "delete_files",
        "create_version",
        "suggest_next_steps",
        "deploy_site",
        "send_message",
    },
}

LLM_FALLBACK_TAGS = {
    "read",
    "search",
    "list",
    "shell",
    "command",
    "browser",
    "web",
    "scrape",
    "console",
    "diff",
    "mcp",
    "resource",
}

HEURISTIC_FALLBACK_TAGS = {
    "final_response",
    "user_visible_output",
    "write",
    "edit",
    "delete",
    "rename",
    "deploy",
    "project",
    "version",
    "dependency",
}


@dataclass(slots=True)
class ToolExecution:
    name: str
    call_id: str
    arguments: dict[str, Any]
    result: Any

    @property
    def content(self) -> str:
        if isinstance(self.result, str):
            return self.result
        return json.dumps(self.result, ensure_ascii=False, sort_keys=True)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def parse_tool_arguments(arguments: Any) -> dict[str, Any]:
    """Parse model tool-call arguments into an object-shaped payload."""
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        stripped = arguments.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return {"value": arguments}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": arguments}


def load_tool_returns(agent: str, agent_root: str | Path = DEFAULT_AGENT_ROOT) -> dict[str, Any]:
    path = Path(agent_root) / slugify_agent(agent) / "tool_returns.json"
    if not path.exists():
        return {}
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {}
    tools = payload.get("tools", payload)
    return tools if isinstance(tools, dict) else {}


def tool_by_name(tools: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for tool in tools:
        if isinstance(tool, dict) and tool.get("name") == name:
            return tool
    return {}


def route_tool(
    *,
    agent: str,
    tool_name: str,
    tool_schema: dict[str, Any] | None = None,
) -> ToolRoute:
    """Choose deterministic heuristic or LLM synthesis for a tool return."""
    if tool_name == "send_message":
        return "heuristic"
    if tool_name in HEURISTIC_TOOLS_BY_AGENT.get(agent, set()):
        return "heuristic"
    if tool_name in LLM_TOOLS_BY_AGENT.get(agent, set()):
        return "llm"

    schema = tool_schema or {}
    if schema.get("terminal") is True or schema.get("host_action") == "final.respond":
        return "heuristic"

    tags = {str(tag).lower() for tag in schema.get("canonical_tags", []) if isinstance(tag, str)}
    host_action = str(schema.get("host_action") or "").lower()
    side_effect = str(schema.get("side_effect") or "").lower()
    name = tool_name.lower()
    text = " ".join([host_action, side_effect, name, *sorted(tags)])

    if any(tag in text for tag in LLM_FALLBACK_TAGS):
        return "llm"
    if any(tag in text for tag in HEURISTIC_FALLBACK_TAGS):
        return "heuristic"
    if side_effect in {"write", "external_write"}:
        return "heuristic"
    return "heuristic"


def render_template(value: Any, *, tool_name: str, arguments: dict[str, Any]) -> Any:
    """Render simple string placeholders inside JSON-like templates."""
    if isinstance(value, dict):
        return {
            key: render_template(item, tool_name=tool_name, arguments=arguments)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [render_template(item, tool_name=tool_name, arguments=arguments) for item in value]
    if not isinstance(value, str):
        return value
    try:
        return value.format(tool_name=tool_name, **arguments)
    except Exception:
        return value


def _first_text_argument(arguments: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def default_heuristic_result(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Return believable, task-neutral host-style output for a stubbed tool."""
    normalized = tool_name.lower()
    if normalized == "send_message":
        return {
            "ok": True,
            "simulated": True,
            "terminal": True,
            "message": "Final response accepted by the benchmark runtime.",
        }

    if any(token in normalized for token in ("search", "grep", "find")):
        query = _first_text_argument(arguments, ("query", "pattern", "search", "text"))
        return {
            "ok": True,
            "simulated": True,
            "query": query,
            "results": [
                {
                    "source": "benchmark_workspace_index",
                    "title": "Repository context",
                    "snippet": "The simulated index is available, but no task-specific evidence was required.",
                    "score": 0.42,
                }
            ],
            "total_results": 1,
        }

    if any(token in normalized for token in ("read", "file")) and "write" not in normalized:
        path = _first_text_argument(arguments, ("path", "file_path", "target_file"))
        return {
            "ok": True,
            "simulated": True,
            "path": path or "workspace/context.txt",
            "exists": True,
            "content_preview": "Simulated workspace content is present but not needed for this AgentIF task.",
            "truncated": False,
        }

    if any(token in normalized for token in ("list", "dir")):
        path = _first_text_argument(arguments, ("path", "directory", "dir"))
        return {
            "ok": True,
            "simulated": True,
            "path": path or ".",
            "entries": [
                {"name": "README.md", "type": "file"},
                {"name": "src", "type": "directory"},
                {"name": "tests", "type": "directory"},
            ],
        }

    if any(token in normalized for token in ("shell", "command", "terminal", "execute")):
        command = _first_text_argument(arguments, ("command", "cmd", "query"))
        return {
            "ok": True,
            "simulated": True,
            "command": command,
            "exit_code": 0,
            "stdout": "Simulated command completed successfully.",
            "stderr": "",
        }

    if any(token in normalized for token in ("write", "edit", "patch", "delete", "rename")):
        path = _first_text_argument(arguments, ("path", "file_path", "target_file"))
        return {
            "ok": True,
            "simulated": True,
            "path": path,
            "mode": "benchmark_dry_run",
            "changed": False,
            "summary": "The host accepted the requested file operation in a dry-run sandbox.",
        }

    if any(token in normalized for token in ("web", "browser", "scrape")):
        query = _first_text_argument(arguments, ("query", "url", "text"))
        return {
            "ok": True,
            "simulated": True,
            "request": query,
            "page_title": "Simulated browser context",
            "summary": "A browser context was opened and contained no task-critical external facts.",
        }

    if any(token in normalized for token in ("deploy", "project", "version", "dependency")):
        return {
            "ok": True,
            "simulated": True,
            "status": "accepted",
            "mode": "benchmark_dry_run",
            "artifact_id": f"stub-{normalized.replace('_', '-')}",
        }

    return {
        "ok": True,
        "simulated": True,
        "tool": tool_name,
        "status": "completed",
        "summary": "The benchmark host returned a generic successful tool result.",
    }


class HeuristicToolExecutor:
    """Execute tool calls through agent-specific or default heuristic returns."""

    def __init__(
        self,
        *,
        agent: str,
        tool_returns: dict[str, Any] | None = None,
        agent_root: str | Path = DEFAULT_AGENT_ROOT,
    ) -> None:
        self.agent = agent
        self.tool_returns = tool_returns if tool_returns is not None else load_tool_returns(agent, agent_root)

    def execute(self, *, call_id: str, name: str, arguments: Any) -> ToolExecution:
        parsed = parse_tool_arguments(arguments)
        template = self.tool_returns.get(name)
        if isinstance(template, dict) and "result" in template:
            result = copy.deepcopy(template["result"])
        elif template is not None:
            result = copy.deepcopy(template)
        else:
            result = default_heuristic_result(name, parsed)
        result = render_template(result, tool_name=name, arguments=parsed)
        return ToolExecution(name=name, call_id=call_id, arguments=parsed, result=result)

