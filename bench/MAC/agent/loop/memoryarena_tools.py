"""MemoryArena WebShop tool execution adapter for the MAC agent loop."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from bench.MAC.agent.loop.tools import ToolExecution, default_heuristic_result, parse_tool_arguments
from bench.MemoryArena.env.env_client import EnvironmentClient


class MemoryArenaWebShopToolExecutor:
    """Execute MemoryArena WebShop actions behind MAC function tools."""

    def __init__(
        self,
        *,
        task: dict[str, Any],
        env_server_url: str = "http://0.0.0.0:8005",
        env_timeout: int = 300,
        upstream_env_server_base: str = "http://127.0.0.1:36004",
        action_format: str = "react",
        max_rounds: int = 25,
        reuse_env: bool = True,
        bootstrap_upstream_env: bool = False,
        enable_feedback: bool = False,
        upstream_webshop_data_root: str | None = None,
        product_catalog_dir: str | None = None,
        domain_data_path: str | None = None,
    ) -> None:
        self.task = task
        self.env_server_url = env_server_url
        self.env_timeout = env_timeout
        self.upstream_env_server_base = upstream_env_server_base
        self.action_format = action_format
        self.max_rounds = max_rounds
        self.reuse_env = reuse_env
        self.bootstrap_upstream_env = bootstrap_upstream_env
        self.enable_feedback = enable_feedback
        self.upstream_webshop_data_root = upstream_webshop_data_root
        self.product_catalog_dir = product_catalog_dir
        self.domain_data_path = domain_data_path
        self.task_id = f"mac-memoryarena-{uuid4()}"
        self._tempdir: tempfile.TemporaryDirectory[str] | None = None
        self._task_file: Path | None = None
        self._env_client: EnvironmentClient | None = None
        self._reset_observation: dict[str, Any] | None = None

    def _write_runtime_task_file(self) -> Path:
        if self._task_file is not None:
            return self._task_file
        task_def = self.task.get("memoryarena_task_def")
        if not isinstance(task_def, dict):
            raise ValueError(f"Task is missing memoryarena_task_def: {self.task.get('task_uid')}")
        self._tempdir = tempfile.TemporaryDirectory(prefix="mac_memoryarena_")
        path = Path(self._tempdir.name) / f"{self.task.get('task_uid', 'task')}.json"
        path.write_text(json.dumps(task_def, ensure_ascii=False, indent=2), encoding="utf-8")
        self._task_file = path
        return path

    def _env_config(self, task_file: Path) -> dict[str, Any]:
        config: dict[str, Any] = {
            "task_file": str(task_file),
            "timeout": self.env_timeout,
            "reuse_env": self.reuse_env,
            "upstream_env_server_base": self.upstream_env_server_base,
            "action_format": self.action_format,
            "max_rounds": self.max_rounds,
            "enable_feedback": self.enable_feedback,
            "bootstrap_upstream_env": self.bootstrap_upstream_env,
        }
        optional_values = {
            "upstream_webshop_data_root": self.upstream_webshop_data_root,
            "product_catalog_dir": self.product_catalog_dir,
            "domain_data_path": self.domain_data_path,
        }
        for key, value in optional_values.items():
            if value:
                config[key] = value
        return config

    def _ensure_env(self) -> EnvironmentClient:
        if self._env_client is not None:
            return self._env_client
        task_file = self._write_runtime_task_file()
        self._env_client = EnvironmentClient(
            task_id=self.task_id,
            env_name="webshop",
            base_url=self.env_server_url,
            timeout=self.env_timeout,
            env_config=self._env_config(task_file),
        )
        self._reset_observation = self._env_client.reset()
        return self._env_client

    @staticmethod
    def _action_from_tool(name: str, arguments: dict[str, Any]) -> str:
        if name == "search":
            keywords = arguments.get("keywords", arguments.get("query", arguments.get("value", "")))
            return f"search[{keywords}]"
        if name == "click":
            item = arguments.get("item", arguments.get("value", ""))
            return f"click[{item}]"
        raise ValueError(f"Unsupported MemoryArena WebShop tool: {name}")

    def execute(self, *, call_id: str, name: str, arguments: Any) -> ToolExecution:
        parsed = parse_tool_arguments(arguments)
        if name == "send_message":
            self.close()
            return ToolExecution(
                name=name,
                call_id=call_id,
                arguments=parsed,
                result=default_heuristic_result(name, parsed),
            )
        if name not in {"search", "click"}:
            return ToolExecution(
                name=name,
                call_id=call_id,
                arguments=parsed,
                result={"ok": False, "error": f"Unsupported MemoryArena WebShop tool: {name}"},
            )

        env = self._ensure_env()
        action = self._action_from_tool(name, parsed)
        result = env.step(
            action,
            ground_truth=self.task.get("target_products"),
            need_judge=True,
        )
        return ToolExecution(
            name=name,
            call_id=call_id,
            arguments=parsed,
            result={
                "ok": True,
                "action": action,
                "initial_observation": self._reset_observation,
                "observation": result.get("observation"),
                "reward": result.get("reward"),
                "done": result.get("done", False),
                "info": result.get("info") or {},
            },
        )

    def close(self) -> None:
        if self._env_client is not None:
            try:
                self._env_client.close()
            finally:
                self._env_client = None
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None
            self._task_file = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
