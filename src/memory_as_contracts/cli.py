from __future__ import annotations

import json

import typer

from memory_as_contracts import __version__
from memory_as_contracts.config import load_config
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
        "db_path": str(config.db_path),
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo("Memory-as-Contracts configuration")
    typer.echo(f"OPENAI_API_KEY set: {payload['openai_api_key_set']}")
    typer.echo(f"OPENAI_BASE_URL: {payload['openai_base_url'] or ''}")
    typer.echo(f"MAC_LLM_MODEL: {payload['llm_model'] or ''}")
    typer.echo(f"MAC_DB_PATH: {payload['db_path']}")


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
    """Add a scoped/lifecycled override edge to a blocked rule."""

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
            span=reason,
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
