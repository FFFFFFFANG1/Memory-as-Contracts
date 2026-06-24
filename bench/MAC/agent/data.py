"""Dataset helpers for MAC agent evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AgentLoopInput:
    task_uid: str
    agent: str
    system_prompt: str
    tools: list[dict[str, Any]]
    user_prompt: str
    past_user_turns: list[dict[str, Any]]
    task: dict[str, Any]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def load_system_config(path: str | Path) -> dict[str, Any]:
    return load_json(path)


def agent_config(system_config: dict[str, Any], agent: str) -> dict[str, Any]:
    agents = system_config.get("agents", {})
    if not isinstance(agents, dict) or agent not in agents:
        raise KeyError(f"No system config for agent: {agent}")
    config = agents[agent]
    if not isinstance(config, dict):
        raise TypeError(f"Invalid system config for agent: {agent}")
    return config


def user_turns(task: dict[str, Any]) -> list[dict[str, Any]]:
    chain = task.get("task_chain", {})
    turns = chain.get("turns") if isinstance(chain, dict) else None
    if not isinstance(turns, list):
        turns = task.get("turns", [])
    return [turn for turn in turns if isinstance(turn, dict) and turn.get("role") == "user"]


def split_past_and_current(
    task: dict[str, Any],
    *,
    turn_index: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    turns = user_turns(task)
    if not turns:
        raise ValueError(f"Task has no user turns: {task.get('task_uid')}")
    if turn_index is None:
        current_pos = len(turns) - 1
    else:
        current_pos = turn_index
        if current_pos < 0:
            current_pos = len(turns) + current_pos
    if current_pos < 0 or current_pos >= len(turns):
        raise IndexError(f"turn_index out of range for {task.get('task_uid')}: {turn_index}")
    return turns[:current_pos], turns[current_pos]


def build_agent_loop_input(
    task: dict[str, Any],
    system_config: dict[str, Any],
    *,
    turn_index: int | None = None,
) -> AgentLoopInput:
    agent = str(task.get("agent_name") or "")
    config = agent_config(system_config, agent)
    system_prompt = config.get("system_prompt")
    if not isinstance(system_prompt, str):
        system_prompt = ""
    tools = config.get("tools", [])
    if not isinstance(tools, list):
        tools = []
    past_turns, current_turn = split_past_and_current(task, turn_index=turn_index)
    content = current_turn.get("content")
    if not isinstance(content, str):
        content = ""
    return AgentLoopInput(
        task_uid=str(task.get("task_uid") or ""),
        agent=agent,
        system_prompt=system_prompt,
        tools=[tool for tool in tools if isinstance(tool, dict)],
        user_prompt=content,
        past_user_turns=past_turns,
        task=task,
    )
