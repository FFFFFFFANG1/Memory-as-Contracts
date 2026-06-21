#!/usr/bin/env python3
"""Infer per-agent tool schemas for the MAC benchmark runtime.

Input:
- agentif_raw_data.json: original, unmodified AgentIF system prompts.
- eval_nonzh_single_turn_tmp.json: the real AgentIF single-turn tasks that will
  be evaluated. This file determines which agents are in scope; its user turns
  are not sent to the tool-schema LLM.

Output:
- eval_step4_agent_tools.json: one stable tool catalog per agent. Every agent
  receives a heuristic `send_message` terminal tool used to submit the final
  user-visible response.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAW_INPUT = Path("bench/MAC/data/agentif_raw_data.json")
DEFAULT_TASK_INPUT = Path("bench/MAC/mid_data/eval_nonzh_single_turn_tmp.json")
DEFAULT_OUTPUT = Path("bench/MAC/mid_data/eval_step4_agent_tools.json")
DEFAULT_CACHE = Path("bench/MAC/mid_data/tool_schema_gen_cache.json")

TOOL_SCHEMA_SYSTEM_PROMPT = """
You design tool schemas for an agent benchmark runtime.

Given one agent's original AgentIF system prompt, infer only the agent-wide tools
that are necessary or clearly supported by the agent's role and runtime
description.

Rules:
- Design a stable per-agent tool catalog, not per-task tools.
- Prefer a minimal tool set. If the system prompt describes a direct-response agent, return no
  optional tools; the benchmark will add a final response tool separately.
- Do not invent task-specific tools like "solve_this_java_problem".
- If the system prompt clearly describes a tool-using coding/browser/sandbox
  environment, include general tools such as shell, file read/write/edit, search,
  browser, console, or preview as appropriate.
- Use simple JSON Schema object input schemas.
- Use generic runtime names, not provider-specific names, unless the system
  prompt makes a native name important.
- Every optional tool must include a low-information simulated stub result. The
  benchmark does not execute real tools.

Return valid JSON only with this schema:
{
  "runtime_family": "response_only|coding|browser|general_computer|analysis|domain_tool|other",
  "needs_react_loop": true|false,
  "tools": [
    {
      "name": "snake_case_tool_name",
      "description": "short description",
      "input_schema": {"type": "object", "properties": {}, "required": []},
      "host_action": "canonical.action",
      "canonical_tags": ["tag"],
      "side_effect": "none|read|write|external_write",
      "stub_result": {"ok": true, "simulated": true}
    }
  ],
  "aliases": {"observed_or_native_name": "snake_case_tool_name"},
}
""".strip()


SEND_MESSAGE_TOOL = {
    "name": "send_message",
    "description": "Submit the final user-visible response for this task. This is a terminal tool.",
    "input_schema": {
        "type": "object",
        "required": ["response"],
        "properties": {
            "response": {
                "type": "string",
                "description": "The complete final answer that should be evaluated as the assistant response.",
            }
        },
        "additionalProperties": False,
    },
    "host_action": "final.respond",
    "canonical_tags": ["final_response", "user_visible_output"],
    "side_effect": "external_write",
    "terminal": True,
    "stub_result": {
        "ok": True,
        "simulated": True,
        "terminal": True,
        "message": "Final response accepted by the benchmark runtime.",
    },
}


def load_json(path: Path, *, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return copy.deepcopy(default)
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_env(env_file: Path | None = None) -> None:
    if env_file:
        load_dotenv(env_file, override=False)
    else:
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
        else:
            load_dotenv(override=False)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def truncate_text(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: limit - 80].rstrip() + "\n...[truncated]..."


def first_message(task: dict[str, Any], role: str) -> str:
    messages = task.get("input", [])
    if not isinstance(messages, list):
        return ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") == role and isinstance(message.get("content"), str):
            return message["content"].strip()
    return ""


def task_uid(task: dict[str, Any]) -> str:
    value = task.get("mac_task_uid", task.get("id", ""))
    return str(value)


def agent_name(task: dict[str, Any]) -> str:
    value = task.get("agent_name")
    return value.strip() if isinstance(value, str) else ""


def raw_system_prompt_index(raw_tasks: list[Any]) -> dict[str, dict[str, Any]]:
    prompts_by_agent: dict[str, set[str]] = defaultdict(set)
    for task in raw_tasks:
        if not isinstance(task, dict):
            continue
        agent = agent_name(task)
        prompt = first_message(task, "system")
        if agent and prompt:
            prompts_by_agent[agent].add(prompt)

    prompts: dict[str, dict[str, Any]] = {}
    for agent, prompts_for_agent in prompts_by_agent.items():
        if len(prompts_for_agent) != 1:
            prompts[agent] = {
                "system_prompt": "",
                "system_prompt_sha256": None,
                "system_prompt_length": 0,
                "multiple_raw_system_prompts": len(prompts_for_agent),
            }
            continue
        prompt = next(iter(prompts_for_agent))
        prompts[agent] = {
            "system_prompt": prompt,
            "system_prompt_sha256": sha256_text(prompt),
            "system_prompt_length": len(prompt),
        }
    return prompts


def collect_real_tasks(tasks: list[Any]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        agent = agent_name(task)
        if not agent:
            continue
        grouped[agent].append({"task_uid": task_uid(task)})
    return {agent: items for agent, items in sorted(grouped.items())}


def build_prompt(
    *,
    agent: str,
    system_prompt: str,
    args: argparse.Namespace,
) -> str:
    payload = {
        "agent": agent,
        "system_prompt_source": "bench/MAC/data/agentif_raw_data.json",
        "system_prompt": truncate_text(system_prompt, args.system_prompt_limit),
        "benchmark_runtime_assumptions": {
            "final_answer_is_tool_bounded": True,
            "send_message_added_by_caller": True,
            "real_tool_execution": False,
            "tool_results_are_simulated_stubs": True,
            "tool_catalog_scope": "agent-wide, stable across all tasks for this agent",
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def call_llm(
    *,
    model: str,
    base_url: str | None,
    api_key: str | None,
    system_prompt: str,
    prompt: str,
    max_tokens: int,
    timeout: float,
    retries: int,
    sleep: float,
) -> str:
    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:
        raise RuntimeError("openai package is required for live tool schema extraction") from exc
    if not model:
        raise ValueError("Missing model. Pass --model or set MAC_LLM_MODEL.")
    if not api_key:
        raise ValueError("Missing API key. Pass --api-key or set OPENAI_API_KEY.")

    client = openai_module.OpenAI(
        api_key=api_key,
        base_url=base_url or None,
        timeout=timeout,
        max_retries=0,
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.0,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - CLI should retry provider/transport errors.
            last_error = exc
            if attempt == retries:
                break
            time.sleep(sleep * (2 ** (attempt - 1)))
    raise RuntimeError(f"LLM request failed after {retries} attempts: {last_error}") from last_error


def parse_llm_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
        if match:
            stripped = match.group(1).strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON root must be an object")
    return payload


def empty_cache() -> dict[str, Any]:
    return {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "items": {},
    }


def cache_key(*, model: str, agent: str, system_prompt: str) -> str:
    return sha256_text(
        stable_json(
            {
                "kind": "agent_tool_schema",
                "model": model,
                "agent": agent,
                "system_prompt_hash": sha256_text(system_prompt),
                "prompt_version": 2,
            }
        )
    )


def load_cache(path: Path) -> dict[str, Any]:
    cache = load_json(path, default=empty_cache())
    if not isinstance(cache, dict):
        raise ValueError(f"Tool schema cache must be a JSON object: {path}")
    if not isinstance(cache.get("items"), dict):
        cache["items"] = {}
    return cache


def cache_record(cache: dict[str, Any], key: str, *, model: str, agent: str, payload: dict[str, Any]) -> None:
    cache["items"][key] = {
        "model": model,
        "agent": agent,
        "payload": payload,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache["updated_at"] = datetime.now(timezone.utc).isoformat()


def normalize_side_effect(value: Any) -> str:
    text = str(value or "none")
    return text if text in {"none", "read", "write", "external_write"} else "none"


def normalize_tool(tool: Any) -> dict[str, Any] | None:
    if not isinstance(tool, dict):
        return None
    name = tool.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip()).strip("_").lower()
    if not name or name == "send_message":
        return None
    schema = tool.get("input_schema")
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}, "required": []}
    if schema.get("type") != "object":
        schema = {"type": "object", "properties": {}, "required": []}
    tags = tool.get("canonical_tags", [])
    if not isinstance(tags, list):
        tags = []
    stub = tool.get("stub_result")
    if not isinstance(stub, dict):
        stub = {"ok": True, "simulated": True}
    stub.setdefault("ok", True)
    stub.setdefault("simulated", True)
    return {
        "name": name,
        "description": str(tool.get("description", "")).strip() or f"Tool available to {name}.",
        "input_schema": schema,
        "host_action": str(tool.get("host_action", name)).strip() or name,
        "canonical_tags": sorted({str(tag) for tag in tags if str(tag).strip()}),
        "side_effect": normalize_side_effect(tool.get("side_effect")),
        "stub_result": stub,
    }


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    runtime_family = str(payload.get("runtime_family", "other")).strip() or "other"
    allowed_families = {
        "response_only",
        "coding",
        "browser",
        "general_computer",
        "analysis",
        "domain_tool",
        "other",
    }
    if runtime_family not in allowed_families:
        runtime_family = "other"
    tools = []
    seen = set()
    for tool in payload.get("tools", []):
        normalized = normalize_tool(tool)
        if normalized is None or normalized["name"] in seen:
            continue
        seen.add(normalized["name"])
        tools.append(normalized)
    aliases = payload.get("aliases", {})
    if not isinstance(aliases, dict):
        aliases = {}
    aliases = {
        str(key): str(value)
        for key, value in aliases.items()
        if str(key).strip() and str(value).strip() and str(value) != "send_message"
    }
    return {
        "runtime_family": runtime_family,
        "needs_react_loop": bool(payload.get("needs_react_loop", bool(tools))),
        "tools": tools,
        "aliases": aliases,
        "rationale": str(payload.get("rationale", "")).strip(),
    }


def append_send_message(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered = [tool for tool in tools if tool.get("name") != "send_message"]
    return [*filtered, copy.deepcopy(SEND_MESSAGE_TOOL)]


def dry_run_payload(agent: str, system_prompt: str) -> dict[str, Any]:
    text = system_prompt.lower()
    toolish = any(
        token in text
        for token in (
            "<tool_calling>",
            "tool call",
            "tools at your disposal",
            "shell",
            "terminal",
            "browser",
            "apply_patch",
            "edit_file",
            "run_terminal_cmd",
        )
    )
    return {
        "runtime_family": "coding" if toolish else "response_only",
        "needs_react_loop": toolish,
        "tools": [],
        "aliases": {},
        "rationale": f"dry-run heuristic for {agent}",
    }


def extract_agent_tools(
    *,
    agent: str,
    system_prompt: str,
    cache: dict[str, Any],
    args: argparse.Namespace,
) -> tuple[dict[str, Any], str]:
    if args.dry_run:
        return dry_run_payload(agent, system_prompt), "dry_run"

    key = cache_key(
        model=args.model or "",
        agent=agent,
        system_prompt=system_prompt,
    )
    cached = cache.get("items", {}).get(key)
    if isinstance(cached, dict) and isinstance(cached.get("payload"), dict):
        return cached["payload"], "hit"

    prompt = build_prompt(
        agent=agent,
        system_prompt=system_prompt,
        args=args,
    )
    raw = call_llm(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        system_prompt=TOOL_SCHEMA_SYSTEM_PROMPT,
        prompt=prompt,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
    )
    payload = normalize_payload(parse_llm_json(raw))
    cache_record(cache, key, model=args.model, agent=agent, payload=payload)
    return payload, "miss"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-input", type=Path, default=DEFAULT_RAW_INPUT)
    parser.add_argument("--task-input", type=Path, default=DEFAULT_TASK_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--model", default=os.getenv("MAC_LLM_MODEL"))
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL") or os.getenv("MAC_LLM_BASE_URL"))
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY"))
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--system-prompt-limit", type=int, default=30000)
    parser.add_argument("--only-agent", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def preparse_env_file() -> Path | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env-file", type=Path, default=None)
    args, _ = parser.parse_known_args()
    return args.env_file


def main() -> int:
    load_env(preparse_env_file())
    args = parse_args()

    raw_input_path = resolve_path(args.raw_input)
    task_input_path = resolve_path(args.task_input)
    output_path = resolve_path(args.output)
    cache_path = resolve_path(args.cache)

    raw_payload = load_json(raw_input_path)
    task_payload = load_json(task_input_path)
    if not isinstance(raw_payload, list):
        raise ValueError(f"Expected JSON list in {raw_input_path}")
    if not isinstance(task_payload, list):
        raise ValueError(f"Expected JSON list in {task_input_path}")

    prompt_index = raw_system_prompt_index(raw_payload)
    real_tasks_by_agent = collect_real_tasks(task_payload)
    agents = sorted(real_tasks_by_agent)
    if args.only_agent:
        agents = [agent for agent in agents if agent in set(args.only_agent)]

    cache = load_cache(cache_path)
    cache_counts = Counter()
    agent_tools: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    skipped: list[dict[str, Any]] = []

    for ordinal, agent in enumerate(agents, start=1):
        prompt_info = prompt_index.get(agent, {})
        system_prompt = str(prompt_info.get("system_prompt", ""))
        real_tasks = real_tasks_by_agent.get(agent, [])
        if not system_prompt:
            reason = (
                f"multiple_raw_system_prompts:{prompt_info['multiple_raw_system_prompts']}"
                if "multiple_raw_system_prompts" in prompt_info
                else "no_raw_system_prompt"
            )
            skipped.append({"agent": agent, "task_count": len(real_tasks), "reason": reason})
            print(f"[{ordinal}/{len(agents)}] agent={agent!r} skipped reason={reason} tasks={len(real_tasks)}")
            continue
        try:
            inferred, cache_status = extract_agent_tools(
                agent=agent,
                system_prompt=system_prompt,
                cache=cache,
                args=args,
            )
            cache_counts[cache_status] += 1
            tools = append_send_message(list(inferred.get("tools", [])))
            agent_tools.append(
                {
                    "agent": agent,
                    "task_count": len(real_tasks),
                    "task_uids": [item["task_uid"] for item in real_tasks],
                    "system_prompt_sha256": prompt_info.get("system_prompt_sha256")
                    or (sha256_text(system_prompt) if system_prompt else None),
                    "system_prompt_length": len(system_prompt),
                    "tool_extraction_cache": cache_status,
                    "runtime_family": inferred.get("runtime_family", "other"),
                    "needs_react_loop": bool(inferred.get("needs_react_loop", False)),
                    "tools": tools,
                    "aliases": inferred.get("aliases", {}),
                    "rationale": inferred.get("rationale", ""),
                }
            )
            print(
                f"[{ordinal}/{len(agents)}] agent={agent!r} cache={cache_status} "
                f"tasks={len(real_tasks)} optional_tools={len(tools) - 1} runtime={inferred.get('runtime_family')}"
            )
        except Exception as exc:  # noqa: BLE001 - keep batch progress visible.
            errors.append({"agent": agent, "error": str(exc)})
            print(f"[{ordinal}/{len(agents)}] agent={agent!r} ERROR {exc}")

    if not args.dry_run:
        write_json(cache_path, cache)

    summary = {
        "total_agents": len(agents),
        "successful_agents": len(agent_tools),
        "failed_agents": len(errors),
        "skipped_agents": len(skipped),
        "agents_with_only_send_message": sum(1 for item in agent_tools if len(item.get("tools", [])) == 1),
        "agents_with_optional_tools": sum(1 for item in agent_tools if len(item.get("tools", [])) > 1),
        "cache_distribution": dict(cache_counts),
    }
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_raw_input": str(raw_input_path.relative_to(REPO_ROOT)),
        "source_task_input": str(task_input_path.relative_to(REPO_ROOT)),
        "summary": summary,
        "send_message_tool": SEND_MESSAGE_TOOL,
        "agent_tools": agent_tools,
        "skipped_agents": skipped,
        "errors": errors,
    }
    if not args.dry_run:
        write_json(output_path, output)
        print(f"wrote {len(agent_tools)} agent tool catalog(s) to {output_path}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
