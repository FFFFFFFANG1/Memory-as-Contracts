from __future__ import annotations

import json

import typer

from memory_as_contracts import __version__
from memory_as_contracts.action_log import ActionLogView
from memory_as_contracts.config import load_config
from memory_as_contracts.logging_config import configure_logging
from memory_as_contracts.models import (
    ContractEdge,
    ContractSource,
    EdgeRelation,
    Lifecycle,
    Scope,
    SourceKind,
    prefixed_id,
)
from memory_as_contracts.store import ContractStore
from memory_as_contracts.validator_generation import ValidatorSnippetPackage
from memory_as_contracts.validator_installation import (
    ValidatorInstaller,
    ValidatorSnippetVerifier,
)
from memory_as_contracts.validators import ValidatorRuntime


app = typer.Typer(
    help="Memory-as-Contracts (MAC): contract layer for memory-mediated agent behavior.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the MAC package version."""

    typer.echo(f"memory-as-contracts {__version__}")


@app.command()
def env(json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON.")) -> None:
    """Show effective MAC configuration without printing secrets."""

    config = load_config()
    payload = {
        "openai_api_key_set": bool(config.openai_api_key),
        "openai_base_url": config.openai_base_url,
        "llm_model": config.llm_model,
        "llm_timeout_seconds": config.llm_timeout_seconds,
        "db_path": str(config.db_path),
        "log_path": str(config.log_path),
        "log_level": config.log_level,
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo("Memory-as-Contracts configuration")
    typer.echo(f"OPENAI_API_KEY set: {payload['openai_api_key_set']}")
    typer.echo(f"OPENAI_BASE_URL: {payload['openai_base_url'] or ''}")
    typer.echo(f"MAC_LLM_MODEL: {payload['llm_model'] or ''}")
    typer.echo(f"MAC_LLM_TIMEOUT_SECONDS: {payload['llm_timeout_seconds']}")
    typer.echo(f"MAC_DB_PATH: {payload['db_path']}")
    typer.echo(f"MAC_LOG_PATH: {payload['log_path']}")
    typer.echo(f"MAC_LOG_LEVEL: {payload['log_level']}")


@app.command("action-log")
def action_log(limit: int = typer.Option(50, min=1, max=1000)) -> None:
    """List recent committed Action Log entries."""

    store = _open_store()
    try:
        entries = store.list_action_log_entries()[-limit:]
        _echo_json([entry.model_dump(mode="json") for entry in entries])
    finally:
        store.close()


@app.command("search-actions")
def search_actions(
    session_id: str = typer.Option(...),
    spec_json: str = typer.Option(..., "--spec-json"),
) -> None:
    """Execute the production ActionLog search translator."""

    store = _open_store()
    try:
        spec = json.loads(spec_json)
        rows = ActionLogView(store, session_id=session_id).search(spec)
        _echo_json(rows)
    finally:
        store.close()


@app.command("validators")
def validators(contract_id: str | None = typer.Option(None)) -> None:
    """List validator versions and installation status."""

    store = _open_store()
    try:
        _echo_json(
            {
                "versions": [
                    version.model_dump(mode="json")
                    for version in store.list_validator_versions(contract_id=contract_id)
                ],
                "installations": [
                    record.model_dump(mode="json")
                    for record in store.list_validator_installations(contract_id)
                ],
            }
        )
    finally:
        store.close()


@app.command("validator-state")
def validator_state(validator_version_id: str = typer.Argument(...)) -> None:
    """Show scoped state and transition provenance for a validator."""

    store = _open_store()
    try:
        _echo_json(
            {
                "states": [
                    state.model_dump(mode="json")
                    for state in store.list_validator_states(validator_version_id)
                ],
                "transitions": [
                    transition.model_dump(mode="json")
                    for transition in store.list_validator_state_transitions(
                        validator_version_id
                    )
                ],
            }
        )
    finally:
        store.close()


@app.command("asks")
def asks() -> None:
    """List incomplete AskRequest records."""

    store = _open_store()
    try:
        records = [
            request.model_dump(mode="json")
            for request in store.list_ask_requests()
            if request.status.value not in {"consumed", "cancelled"}
        ]
        _echo_json(records)
    finally:
        store.close()


@app.command("validator-errors")
def validator_errors(
    validator_version_id: str | None = typer.Option(None),
) -> None:
    """List validator runtime errors and replay requirements."""

    store = _open_store()
    try:
        _echo_json(
            [
                error.model_dump(mode="json")
                for error in store.list_validator_runtime_errors(validator_version_id)
            ]
        )
    finally:
        store.close()


@app.command("verify-validator")
def verify_validator(
    contract_id: str = typer.Argument(...),
    package_json: str = typer.Option(..., "--package-json"),
    session_id: str = typer.Option(...),
    task_id: str | None = typer.Option(None),
) -> None:
    """Run validator verification without installing a version."""

    store = _open_store()
    try:
        contract = _require_contract(store, contract_id)
        package = ValidatorSnippetPackage.model_validate_json(package_json)
        result = ValidatorSnippetVerifier().verify(
            contract,
            package,
            store=store,
            session_id=session_id,
            task_id=task_id,
            committed_examples=store.list_action_log_entries(),
        )
        _echo_json(result.model_dump(mode="json"))
    finally:
        store.close()


@app.command("install-validator")
def install_validator(
    contract_id: str = typer.Argument(...),
    package_json: str = typer.Option(..., "--package-json"),
    session_id: str = typer.Option(...),
    task_id: str | None = typer.Option(None),
) -> None:
    """Verify and transactionally install a validator version."""

    store = _open_store()
    try:
        contract = _require_contract(store, contract_id)
        package = ValidatorSnippetPackage.model_validate_json(package_json)
        result = ValidatorInstaller().register(
            contract,
            package,
            store=store,
            session_id=session_id,
            task_id=task_id,
        )
        _echo_json(
            {
                "status": result.status,
                "errors": result.errors,
                "validator_version": result.validator_version.model_dump(mode="json")
                if result.validator_version is not None
                else None,
            }
        )
    finally:
        store.close()


@app.command("replay-validator")
def replay_validator(
    validator_version_id: str = typer.Argument(...),
    scope_key: str = typer.Option(...),
) -> None:
    """Rebuild one scoped validator state from committed Action Log entries."""

    store = _open_store()
    try:
        version = store.get_validator_version(validator_version_id)
        if version is None:
            raise typer.BadParameter(f"unknown validator version: {validator_version_id}")
        state = ValidatorRuntime(store).rebuild_state(version, scope_key)
        _echo_json(state.model_dump(mode="json"))
    finally:
        store.close()


@app.command("mac_rule_override")
def mac_rule_override(
    rule_id: str = typer.Argument(..., help="Blocked rule/contract id to override."),
    scope_json: str = typer.Option(
        ...,
        "--scope-json",
        help="JSON Scope for the override edge.",
    ),
    lifecycle_json: str = typer.Option(
        ...,
        "--lifecycle-json",
        help="JSON Lifecycle for the override edge.",
    ),
    reason: str = typer.Option(
        "agent override after approval or sufficient evidence",
        "--reason",
        help="Why this override is justified.",
    ),
    source_kind: SourceKind = typer.Option(
        SourceKind.AGENT_INFERRED,
        "--source-kind",
        help="Override provenance.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Add a scoped/lifecycled override edge to a rejected rule."""

    config = load_config()
    store = ContractStore(config.db_path)
    store.init_db()
    contract = store.get_contract(rule_id)
    if contract is None:
        raise typer.BadParameter(f"unknown rule id: {rule_id}")

    scope = _parse_model_json(scope_json, Scope, "scope-json")
    lifecycle = _parse_model_json(lifecycle_json, Lifecycle, "lifecycle-json")
    edge = ContractEdge(
        from_contract=prefixed_id("OVERRIDE"),
        to_contract=rule_id,
        relation=EdgeRelation.OVERRIDE,
        scope=scope,
        lifecycle=lifecycle,
        source=ContractSource(
            kind=source_kind,
            metadata={"override_reason": reason},
        ),
    )
    store.add_edge(edge)

    payload = {
        "edge_id": edge.id,
        "relation": edge.relation.value,
        "from_contract": edge.from_contract,
        "to_contract": edge.to_contract,
        "scope": edge.scope.model_dump(mode="json"),
        "lifecycle": edge.lifecycle.model_dump(mode="json"),
        "reason": reason,
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"Created override edge {edge.id} for rule {rule_id}")


def _parse_model_json(raw: str, model_class, label: str):
    try:
        return model_class.model_validate_json(raw)
    except Exception as exc:
        raise typer.BadParameter(f"invalid {label}: {exc}") from exc


def _open_store() -> ContractStore:
    config = load_config()
    configure_logging(path=config.log_path, level=config.log_level)
    store = ContractStore(config.db_path)
    store.init_db()
    return store


def _require_contract(store: ContractStore, contract_id: str):
    contract = store.get_contract(contract_id)
    if contract is None:
        raise typer.BadParameter(f"unknown contract: {contract_id}")
    return contract


def _json_list(raw: str, label: str) -> list[dict]:
    payload = json.loads(raw)
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise typer.BadParameter(f"{label} must be a JSON list of objects")
    return payload


def _echo_json(payload) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
