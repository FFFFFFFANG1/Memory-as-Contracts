from __future__ import annotations

import hashlib
import json
import logging
import os
import resource
import select
import subprocess
import sys
import tempfile
import textwrap
import time
from typing import Any

from memory_as_contracts.action_log import ActionLogView
from memory_as_contracts.logging_config import log_event
from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionSignature,
    GateDecisionType,
    ValidatorRuntimeErrorRecord,
    ValidatorState,
    ValidatorStateTransition,
    ValidatorVerdict,
    ValidatorVersion,
)
from memory_as_contracts.store import ContractStore
from memory_as_contracts.validator_dispatch import (
    ValidatorDispatchPlanner,
    validator_scope_key_for_signature,
)

LOGGER = logging.getLogger(__name__)


class ValidatorRuntime:
    """Runtime facade for installed validator versions."""

    def __init__(self, store: ContractStore) -> None:
        self.store = store
        self.runner = ValidatorSandboxRunner()
        self.dispatch = ValidatorDispatchPlanner(store)

    def record_committed_action(self, entry: ActionLogEntryV1) -> ActionLogEntryV1:
        stored, inserted = self.store.append_action_log_entry(entry)
        if not inserted:
            return stored
        for plan in self.dispatch.for_committed_entry(stored):
            version = plan.version
            scope_key = plan.scope_key
            try:
                self.update(version, stored, scope_key=scope_key)
            except (ValidatorSandboxError, ValueError, RuntimeError) as exc:
                state = self.store.get_validator_state(version.id, scope_key)
                degraded = ValidatorState(
                    validator_version_id=version.id,
                    scope_key=scope_key,
                    contract_id=version.contract_id,
                    state=state.state if state is not None else version.shared_states,
                    revision=state.revision if state is not None else 0,
                    last_applied_seq=state.last_applied_seq if state is not None else None,
                    degraded=True,
                )
                self.store.put_validator_state(
                    degraded,
                    expected_revision=state.revision if state is not None else None,
                )
                self.store.add_validator_runtime_error(
                    ValidatorRuntimeErrorRecord(
                        validator_version_id=version.id,
                        contract_id=version.contract_id,
                        scope_key=scope_key,
                        phase="post_action_update",
                        action_log_seq=stored.seq,
                        error_type=exc.__class__.__name__,
                        message=str(exc),
                        replay_required=True,
                    )
                )
                log_event(
                    LOGGER,
                    "validator.state_degraded",
                    level=logging.ERROR,
                    validator_version_id=version.id,
                    contract_id=version.contract_id,
                    scope_key=scope_key,
                    action_log_seq=stored.seq,
                    error_type=exc.__class__.__name__,
                    replay_required=True,
                )
        return stored

    def check(
        self,
        version: ValidatorVersion,
        signature: ActionSignature,
        *,
        ask_response_flag: bool = False,
        ask_request_id: str | None = None,
    ) -> ValidatorVerdict:
        contract = self.store.get_contract(version.contract_id)
        if contract is None:
            raise ValueError(f"validator contract not found: {version.contract_id}")
        scope_key = validator_scope_key_for_signature(contract, signature)
        state = self.store.get_validator_state(version.id, scope_key)
        if version.update_patterns:
            state = self._catch_up_state(version, scope_key, state)
        if state is not None and state.degraded:
            return ValidatorVerdict(
                decision=GateDecisionType.ASK,
                reason=f"Validator state for rule {version.contract_id} is stale or degraded.",
                evidence_refs=[
                    {
                        "validator_version_id": version.id,
                        "scope_key": scope_key,
                        "last_applied_seq": state.last_applied_seq,
                    }
                ],
                confidence=0.0,
            )
        log = ActionLogView(
            self.store,
            session_id=signature.session.session_id,
        )
        return self.runner.check(
            version,
            action=_pending_action_view(signature),
            state=state.state if state is not None else version.shared_states,
            log=log,
            context={
                "contract_id": version.contract_id,
                "validator_version_id": version.id,
                "ask_response_flag": ask_response_flag,
                "ask_request_id": ask_request_id,
                "scope_key": scope_key,
            },
        )

    def _catch_up_state(
        self,
        version: ValidatorVersion,
        scope_key: str,
        state: ValidatorState | None,
    ) -> ValidatorState | None:
        last_applied_seq = state.last_applied_seq if state is not None else None
        plans = [
            plan
            for plan in self.dispatch.for_replay(version, scope_key=scope_key)
            if plan.entry.seq is not None
            and (last_applied_seq is None or plan.entry.seq > last_applied_seq)
        ]
        if not plans:
            return state
        current = state
        for plan in plans:
            try:
                current = self.update(version, plan.entry, scope_key=scope_key)
            except (ValidatorSandboxError, ValueError, RuntimeError) as exc:
                current = self._mark_state_degraded(
                    version,
                    scope_key,
                    current,
                    phase="pre_action_catchup",
                    action_log_seq=plan.entry.seq,
                    error=exc,
                )
                break
        return current

    def _mark_state_degraded(
        self,
        version: ValidatorVersion,
        scope_key: str,
        state: ValidatorState | None,
        *,
        phase: str,
        action_log_seq: int | None,
        error: Exception,
    ) -> ValidatorState:
        degraded = ValidatorState(
            validator_version_id=version.id,
            scope_key=scope_key,
            contract_id=version.contract_id,
            state=state.state if state is not None else version.shared_states,
            revision=state.revision if state is not None else 0,
            last_applied_seq=state.last_applied_seq if state is not None else None,
            degraded=True,
        )
        stored = self.store.put_validator_state(
            degraded,
            expected_revision=state.revision if state is not None else None,
        )
        self.store.add_validator_runtime_error(
            ValidatorRuntimeErrorRecord(
                validator_version_id=version.id,
                contract_id=version.contract_id,
                scope_key=scope_key,
                phase=phase,
                action_log_seq=action_log_seq,
                error_type=error.__class__.__name__,
                message=str(error),
                replay_required=True,
            )
        )
        return stored

    def update(
        self,
        version: ValidatorVersion,
        entry: ActionLogEntryV1,
        *,
        scope_key: str,
    ) -> ValidatorState:
        state = self.store.get_validator_state(version.id, scope_key)
        if (
            state is not None
            and entry.seq is not None
            and state.last_applied_seq is not None
            and entry.seq <= state.last_applied_seq
        ):
            return state
        log = ActionLogView(self.store, session_id=entry.session_id)
        new_state = self.runner.update(
            version,
            state=state.state if state is not None else version.shared_states,
            entry=entry.model_dump(mode="json"),
            log=log,
            context={
                "contract_id": version.contract_id,
                "validator_version_id": version.id,
                "scope_key": scope_key,
            },
        )
        previous_revision = state.revision if state is not None else 0
        next_state = ValidatorState(
            validator_version_id=version.id,
            scope_key=scope_key,
            contract_id=version.contract_id,
            state=new_state,
            revision=previous_revision + 1,
            last_applied_seq=entry.seq,
        )
        stored = self.store.put_validator_state(
            next_state,
            expected_revision=previous_revision if state is not None else None,
        )
        if entry.seq is not None:
            self.store.add_validator_state_transition(
                ValidatorStateTransition(
                    validator_version_id=version.id,
                    scope_key=scope_key,
                    action_log_seq=entry.seq,
                    from_revision=previous_revision,
                    to_revision=stored.revision,
                    state_hash=hashlib.sha256(
                        json.dumps(stored.state, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                )
            )
        return stored

    def rebuild_state(
        self,
        version: ValidatorVersion,
        scope_key: str | None = None,
    ) -> ValidatorState:
        contract = self.store.get_contract(version.contract_id)
        if contract is None:
            raise ValueError(f"validator contract not found: {version.contract_id}")
        if scope_key is None:
            states = self.store.list_validator_states(version.id)
            if len(states) != 1:
                raise ValueError("scope_key is required when a validator has multiple states")
            scope_key = states[0].scope_key
        self.store.delete_validator_state(version.id, scope_key)
        state: dict[str, Any] = dict(version.shared_states)
        revision = 0
        last_applied_seq = None
        for plan in self.dispatch.for_replay(version, scope_key=scope_key):
            entry = plan.entry
            log = ActionLogView(self.store, session_id=entry.session_id)
            state = self.runner.update(
                version,
                state=state,
                entry=entry.model_dump(mode="json"),
                log=log,
                context={
                    "contract_id": version.contract_id,
                    "validator_version_id": version.id,
                    "replay": True,
                },
            )
            revision += 1
            last_applied_seq = entry.seq
        return self.store.put_validator_state(
            ValidatorState(
                validator_version_id=version.id,
                scope_key=scope_key,
                contract_id=version.contract_id,
                state=state,
                revision=revision,
                last_applied_seq=last_applied_seq,
            )
        )


class InProcessValidatorRunner:
    """Backward-compatible alias for the Stage 2 sandbox runner."""

    def __new__(cls, *args: Any, **kwargs: Any) -> "ValidatorSandboxRunner":
        return ValidatorSandboxRunner(*args, **kwargs)


class ValidatorSandboxError(RuntimeError):
    """Raised when a validator snippet fails inside the sandbox."""


class ValidatorSandboxRunner:
    """Run validator snippets in an isolated Python child process."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 2.0,
        max_queries: int = 8,
        max_total_rows: int = 200,
        max_message_bytes: int = 1_000_000,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_queries = max_queries
        self.max_total_rows = max_total_rows
        self.max_message_bytes = max_message_bytes

    def check(
        self,
        version: ValidatorVersion,
        *,
        action: dict[str, Any],
        state: dict[str, Any],
        log: ActionLogView,
        context: dict[str, Any],
    ) -> ValidatorVerdict:
        return ValidatorVerdict.model_validate(
            _normalize_verdict_payload(
                self._run(
                    {
                        "mode": "check",
                        "code": version.check_code,
                        "action": action,
                        "state": state,
                        "state_keys": list(version.shared_states),
                        "context": context,
                    },
                    log,
                )
            )
        )

    def update(
        self,
        version: ValidatorVersion,
        *,
        state: dict[str, Any],
        entry: dict[str, Any],
        log: ActionLogView,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if not version.update_code:
            raise ValueError("validator update_code is not installed")
        result = self._run(
            {
                "mode": "update",
                "code": version.update_code,
                "entry": entry,
                "state": state,
                "state_keys": list(version.shared_states),
                "context": context,
            },
            log,
        )
        if not isinstance(result, dict):
            raise ValueError("validator update must return state dict")
        return result

    def inspect_check(
        self,
        version: ValidatorVersion,
        *,
        action: dict[str, Any],
        state: dict[str, Any],
        log: ActionLogView,
        context: dict[str, Any],
    ) -> tuple[ValidatorVerdict, dict[str, Any]]:
        result = self._run(
            {
                "mode": "check_inspect",
                "code": version.check_code,
                "action": action,
                "state": state,
                "state_keys": list(version.shared_states),
                "context": context,
            },
            log,
        )
        if not isinstance(result, dict) or not isinstance(result.get("state"), dict):
            raise ValidatorSandboxError("validator check inspection returned invalid state")
        verdict = ValidatorVerdict.model_validate(
            _normalize_verdict_payload(result.get("verdict"))
        )
        return verdict, result["state"]

    def _run(self, payload: dict[str, Any], log: ActionLogView) -> Any:
        encoded = json.dumps(payload, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > self.max_message_bytes:
            raise ValidatorSandboxError("validator sandbox input exceeds message limit")
        with tempfile.TemporaryDirectory(prefix="mac-validator-") as cwd:
            process = subprocess.Popen(
                [sys.executable, "-I", "-c", SANDBOX_WORKER],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                env={},
                preexec_fn=_apply_sandbox_resource_limits,
            )
            assert process.stdin is not None
            assert process.stdout is not None
            process.stdin.write(encoded + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + self.timeout_seconds
            query_count = 0
            total_rows = 0
            output_bytes = 0
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ValidatorSandboxError("validator snippet timed out")
                    ready, _, _ = select.select([process.stdout], [], [], remaining)
                    if not ready:
                        raise ValidatorSandboxError("validator snippet timed out")
                    line = process.stdout.readline()
                    if not line:
                        stderr = process.stderr.read() if process.stderr is not None else ""
                        raise ValidatorSandboxError(
                            f"validator sandbox process failed: {stderr.strip()}"
                        )
                    output_bytes += len(line.encode("utf-8"))
                    if output_bytes > self.max_message_bytes:
                        raise ValidatorSandboxError("validator sandbox output exceeds message limit")
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise ValidatorSandboxError(
                            "validator sandbox returned invalid protocol JSON"
                        ) from exc
                    if message.get("type") in {"read", "search"}:
                        query_count += 1
                        if query_count > self.max_queries:
                            self._send_search_response(
                                process,
                                message,
                                error="validator search query budget exceeded",
                            )
                            continue
                        try:
                            rows = log.search(message.get("spec") or {})
                            total_rows += len(rows)
                            if total_rows > self.max_total_rows:
                                raise ValueError("validator search row budget exceeded")
                            self._send_search_response(process, message, rows=rows)
                        except ValueError as exc:
                            self._send_search_response(process, message, error=str(exc))
                        continue
                    if message.get("type") != "result":
                        raise ValidatorSandboxError("validator sandbox returned unknown message")
                    if not message.get("ok"):
                        raise ValidatorSandboxError(
                            f"{message.get('error_type', 'sandbox_error')}: "
                            f"{message.get('error')}"
                        )
                    process.wait(timeout=max(0.1, deadline - time.monotonic()))
                    return message.get("result")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def _send_search_response(
        self,
        process: subprocess.Popen[str],
        request: dict[str, Any],
        *,
        rows: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> None:
        assert process.stdin is not None
        response = {
            "type": "search_result",
            "id": request.get("id"),
            "ok": error is None,
            "rows": rows or [],
            "error": error,
        }
        encoded = json.dumps(response, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > self.max_message_bytes:
            encoded = json.dumps(
                {
                    "type": "search_result",
                    "id": request.get("id"),
                    "ok": False,
                    "rows": [],
                    "error": "validator search response exceeds message limit",
                }
            )
        process.stdin.write(encoded + "\n")
        process.stdin.flush()


def _apply_sandbox_resource_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1_000_000, 1_000_000))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (256_000_000, 256_000_000))
    except (ValueError, OSError):
        pass
    os.umask(0o077)


def _normalize_verdict_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    refs = normalized.get("evidence_refs")
    if isinstance(refs, list):
        normalized["evidence_refs"] = [
            ref if isinstance(ref, dict) else {"value": ref}
            for ref in refs
        ]
    return normalized


SANDBOX_WORKER = textwrap.dedent(
    r"""
    import json
    import math
    import re
    import sys

    def send(message):
        sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    class ValidatorLog:
        def __init__(self, state, state_keys, mode):
            self.request_id = 0
            self.state = state
            self.state_keys = set(state_keys)
            self.mode = mode

        def read(self, spec):
            self.request_id += 1
            request_id = self.request_id
            send({"type": "read", "id": request_id, "spec": spec})
            line = sys.stdin.readline()
            if not line:
                raise RuntimeError("action log read parent disconnected")
            response = json.loads(line)
            if response.get("type") != "search_result" or response.get("id") != request_id:
                raise RuntimeError("invalid action log read response")
            if not response.get("ok"):
                raise ValueError(response.get("error") or "action log read failed")
            return response.get("rows") or []

        def state_read(self, key=None):
            if key is None:
                return dict(self.state)
            if key not in self.state_keys:
                raise KeyError(f"unknown shared state key: {key}")
            return self.state.get(key)

        def state_write(self, updates):
            if self.mode != "update":
                raise RuntimeError("state_write is only available in update")
            if not isinstance(updates, dict):
                raise TypeError("state_write expects a dict of updates")
            unknown = set(updates) - self.state_keys
            if unknown:
                raise KeyError(f"unknown shared state key: {sorted(unknown)[0]}")
            self.state.update(updates)
            return dict(self.state)

    def verdict(decision):
        def make(reason, evidence_refs=None, confidence=1.0):
            return {
                "decision": decision,
                "reason": reason,
                "evidence_refs": evidence_refs or [],
                "confidence": confidence,
            }

        return make

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "math":
            return math
        if name == "re":
            return re
        raise ImportError(f"import not allowed: {name}")

    safe_builtins = {
        "__import__": guarded_import,
        "Exception": Exception,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "format": format,
        "getattr": getattr,
        "hasattr": hasattr,
        "int": int,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
    }

    payload = json.loads(sys.stdin.readline())
    namespace = {
        "__builtins__": safe_builtins,
        "__name__": "__mac_validator__",
        "allow": verdict("allow"),
        "ask": verdict("ask"),
        "reject": verdict("reject"),
        "math": math,
        "re": re,
    }
    try:
        exec(payload["code"], namespace, namespace)
        state = dict(payload.get("state") or {})
        log = ValidatorLog(state, payload.get("state_keys") or [], payload.get("mode"))
        context = dict(payload.get("context") or {})
        if payload["mode"] in {"check", "check_inspect"}:
            check = namespace.get("check")
            if not callable(check):
                raise ValueError("validator snippet must define check")
            result = check(payload.get("action") or {}, log, context)
            if payload["mode"] == "check_inspect":
                result = {"verdict": result, "state": state}
        elif payload["mode"] == "update":
            update = namespace.get("update")
            if not callable(update):
                raise ValueError("validator snippet must define update")
            update(payload.get("entry") or {}, log, context)
            result = state
        else:
            raise ValueError(f"unknown sandbox mode: {payload['mode']}")
        send({"type": "result", "ok": True, "result": result})
    except BaseException as exc:
        send(
            {
                "type": "result",
                "ok": False,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )
    """
)


def _verdict_factory(decision: GateDecisionType):
    def make(
        reason: str,
        evidence_refs: list[dict[str, Any]] | None = None,
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        return {
            "decision": decision.value,
            "reason": reason,
            "evidence_refs": evidence_refs or [],
            "confidence": confidence,
        }

    return make


def _pending_action_view(signature: ActionSignature) -> dict[str, Any]:
    payload = signature.model_dump(mode="json")
    payload["tool_name"] = signature.tool.name
    payload["host_action"] = signature.host_action
    payload["arguments"] = signature.tool.raw_arguments
    return payload
