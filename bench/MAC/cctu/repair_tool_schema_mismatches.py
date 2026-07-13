"""Repair CCTU tool schema / simulator mismatches found by audit_tool_schema.

Fixes applied:
1. Add simulator-required params to schema.required
2. For enum properties: set default + enrich description with allowed values
3. For object filters (date_range / time_period / date): keep required in schema;
   simulator soft-fails with a rich message when missing (via call-error enrichment)
4. For schema properties absent from simulator signatures: accept **kwargs

Does not change suggest-mode control flow.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any

from bench.MAC.cctu.audit_tool_schema import (
    DEFAULT_INPUT_DATA,
    DEFAULT_MAC_TASKS,
    audit_tool_pair,
    parse_simulator_signature,
    tool_name_from_entry,
    tool_schema_from_entry,
)
from bench.MAC.cctu.bridge import parse_cctu_codes

ENUM_DEFAULT_PREFERENCE = {
    "data_source": ("UN", "Ethnologue", "World Bank", "Census"),
    "election_type": ("presidential", "parliamentary", "local", "referendum", "by-election"),
    "sport_type": ("football", "cricket", "basketball", "tennis", "rugby", "baseball", "hockey", "golf"),
    "region_type": ("country", "city", "province", "state", "continent", "empire"),
    "data_type": ("population", "age_distribution", "growth_rate", "density"),
    "event_type": ("treaty", "war", "agreement", "conference", "declaration"),
    "metric": ("MT/s", "GB/s"),
}


def _preferred_enum_default(param: str, enum_values: list[Any]) -> Any:
    preferred = ENUM_DEFAULT_PREFERENCE.get(param, ())
    for value in preferred:
        if value in enum_values:
            return value
    return enum_values[0]


def _ensure_description_mentions_required(
    description: str,
    *,
    enum_values: list[Any] | None = None,
    preferred: Any | None = None,
) -> str:
    text = (description or "").strip()
    extras: list[str] = []
    if "required" not in text.lower():
        extras.append("Required.")
    if enum_values:
        rendered = ", ".join(json.dumps(value, ensure_ascii=False) for value in enum_values)
        marker = f"Allowed values: {rendered}."
        if "allowed values:" not in text.lower():
            extras.append(marker)
        prefer_value = preferred if preferred is not None else enum_values[0]
        unsure = f"If unsure, prefer {json.dumps(prefer_value, ensure_ascii=False)}."
        if "if unsure, prefer" in text.lower():
            text = re.sub(r"If unsure, prefer .*?\.", unsure, text, flags=re.IGNORECASE)
        else:
            extras.append(unsure)
    if not extras:
        return text
    if text and not text.endswith("."):
        text += "."
    return (text + " " + " ".join(extras)).strip()


def _patch_schema_for_required_param(schema: dict[str, Any], param: str) -> bool:
    changed = False
    properties = schema.setdefault("properties", {})
    if not isinstance(properties, dict):
        properties = {}
        schema["properties"] = properties
    prop = properties.get(param)
    if not isinstance(prop, dict):
        prop = {"type": "string", "description": f"Required parameter `{param}`."}
        properties[param] = prop
        changed = True

    required = schema.get("required")
    if not isinstance(required, list):
        required = []
    if param not in required:
        required = list(required) + [param]
        schema["required"] = required
        changed = True

    enum_values = prop.get("enum") if isinstance(prop.get("enum"), list) else None
    preferred = _preferred_enum_default(param, enum_values) if enum_values else None
    new_description = _ensure_description_mentions_required(
        str(prop.get("description") or ""),
        enum_values=enum_values,
        preferred=preferred,
    )
    if new_description != prop.get("description"):
        prop["description"] = new_description
        changed = True

    if enum_values and preferred is not None and prop.get("default") != preferred:
        prop["default"] = preferred
        changed = True

    if param in {"date_range", "date"} and prop.get("type") == "object":
        hint = 'Use {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}.'
        desc = str(prop.get("description") or "")
        if "start_date" not in desc:
            prop["description"] = (desc.rstrip(". ") + ". " + hint).strip()
            changed = True
    if param == "time_period" and prop.get("type") == "object":
        hint = 'Use {"start_year": YYYY, "end_year": YYYY}.'
        desc = str(prop.get("description") or "")
        if "start_year" not in desc:
            prop["description"] = (desc.rstrip(". ") + ". " + hint).strip()
            changed = True
    return changed


def _add_kwargs_to_simulator(code: str) -> tuple[str, bool]:
    parsed = parse_simulator_signature(code)
    if parsed is None or parsed.has_varkw:
        return code, False
    match = re.search(r"def\s+\w+\s*\((.*?)\)\s*:", code, flags=re.S)
    if not match:
        return code, False
    params = match.group(1).rstrip()
    if "**" in params:
        return code, False
    if params.strip():
        if not params.rstrip().endswith(","):
            replacement = params.rstrip() + ", **kwargs"
        else:
            replacement = params.rstrip() + " **kwargs"
    else:
        replacement = "**kwargs"
    new_code = code[: match.start(1)] + replacement + code[match.end(1) :]
    return new_code, new_code != code


def _soft_default_trailing_object_filters(code: str, params: set[str]) -> tuple[str, bool]:
    """Make object-like filters default to None when syntactically legal.

    Converts from the earliest requested object-filter in the required-prefix through
    the end of that prefix (including any following required params), so Python
    signature validity is preserved. Injects a soft-fail guard for each converted
    parameter.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, False
    func = next((node for node in tree.body if isinstance(node, ast.FunctionDef)), None)
    if func is None:
        return code, False

    args = func.args
    defaults_offset = len(args.args) - len(args.defaults)
    required_args = args.args[:defaults_offset]
    required_names = [arg.arg for arg in required_args]
    object_indices = [index for index, name in enumerate(required_names) if name in params]
    if not object_indices:
        return code, False
    convertible = required_names[min(object_indices) :]
    if not convertible:
        return code, False

    match = re.search(r"def\s+" + re.escape(func.name) + r"\s*\((.*?)\)\s*:", code, flags=re.S)
    if not match:
        return code, False
    param_blob = match.group(1)
    new_blob = param_blob
    for name in convertible:
        pattern = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)(?!\s*=)")
        new_blob, count = pattern.subn(f"{name}=None", new_blob, count=1)
        if count != 1:
            return code, False

    if f"if {convertible[0]} is None:" in code:
        new_code = code[: match.start(1)] + new_blob + code[match.end(1) :]
        return new_code, new_code != code

    guard_lines = []
    for name in convertible:
        if name in {"date_range", "date"}:
            expected = '{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}'
        elif name == "time_period":
            expected = '{"start_year": YYYY, "end_year": YYYY}'
        else:
            expected = "a non-null value"
        message = f"Error: '{name}' is required. Expected {expected}."
        guard_lines.append(f"    if {name} is None:\n        return {json.dumps(message)}")
    guard_block = "\n".join(guard_lines) + "\n"

    def_end = match.end()
    rest = code[def_end:]
    docstring_match = re.match(r"\s*(?:\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?''')\s*\n", rest)
    insert_at = def_end + (docstring_match.end() if docstring_match else (1 if rest.startswith("\n") else 0))
    if rest.startswith("\n") and not docstring_match:
        insert_at = def_end + 1

    new_code = (
        code[: match.start(1)]
        + new_blob
        + code[match.end(1) : insert_at]
        + guard_block
        + code[insert_at:]
    )
    return new_code, True


def repair_task_tools_and_codes(
    *,
    codes: dict[str, str],
    tools: list[dict[str, Any]],
) -> tuple[dict[str, str], list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    schemas: dict[str, dict[str, Any]] = {}
    for tool in tools:
        name = tool_name_from_entry(tool)
        if name:
            schemas[name] = tool_schema_from_entry(tool)

    new_codes = dict(codes)
    for tool_name, code in list(codes.items()):
        schema = schemas.get(tool_name)
        issues = audit_tool_pair(
            task_id="tmp",
            tool_name=tool_name,
            schema=schema,
            code=code,
        )
        if not issues:
            continue

        object_params = {
            issue.param
            for issue in issues
            if issue.kind == "sim_required_not_in_schema_required"
            and issue.param in {"date_range", "time_period", "date"}
        }
        required_params = {
            issue.param
            for issue in issues
            if issue.kind == "sim_required_not_in_schema_required" and issue.param
        }
        prop_extra = {
            issue.param
            for issue in issues
            if issue.kind == "schema_prop_not_in_sim" and issue.param
        }

        if schema is not None:
            for param in sorted(required_params):
                if _patch_schema_for_required_param(schema, param):
                    notes.append(f"{tool_name}: schema.required += {param}")

        updated_code = code
        if object_params:
            updated_code, changed = _soft_default_trailing_object_filters(updated_code, object_params)
            if changed:
                notes.append(f"{tool_name}: simulator default None for {sorted(object_params)}")
        if prop_extra:
            updated_code, changed = _add_kwargs_to_simulator(updated_code)
            if changed:
                notes.append(f"{tool_name}: simulator accepts **kwargs for {sorted(prop_extra)}")
        if updated_code != code:
            new_codes[tool_name] = updated_code

    # Write schemas back into tool entries.
    new_tools: list[dict[str, Any]] = []
    for tool in tools:
        cloned = json.loads(json.dumps(tool))
        name = tool_name_from_entry(cloned)
        if name and name in schemas:
            schema = schemas[name]
            if cloned.get("type") == "function" and isinstance(cloned.get("function"), dict):
                cloned["function"]["parameters"] = schema
            elif "input_schema" in cloned:
                cloned["input_schema"] = schema
            elif "parameters" in cloned:
                cloned["parameters"] = schema
        new_tools.append(cloned)
    return new_codes, new_tools, notes


def repair_input_data(path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    all_notes: list[str] = []
    changed_tasks = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        codes = parse_cctu_codes(row.get("codes"))
        tools_raw = row.get("tools")
        tools = json.loads(tools_raw) if isinstance(tools_raw, str) else tools_raw
        if not isinstance(tools, list):
            rows.append(row)
            continue
        new_codes, new_tools, notes = repair_task_tools_and_codes(codes=codes, tools=tools)
        if notes:
            changed_tasks += 1
            all_notes.extend(f"task {row.get('id')}: {note}" for note in notes)
            row["codes"] = json.dumps(new_codes, ensure_ascii=False)
            row["tools"] = json.dumps(new_tools, ensure_ascii=False)
        rows.append(row)

    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return {"changed_tasks": changed_tasks, "notes": all_notes, "path": str(path)}


def sync_mac_task_schemas(*, input_data: Path, mac_tasks: Path) -> dict[str, Any]:
    samples: dict[str, dict[str, Any]] = {}
    for line in input_data.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        samples[str(row.get("id"))] = row

    payload = json.loads(mac_tasks.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError(f"Unexpected mac tasks payload: {mac_tasks}")

    changed = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        cctu_id = str(task.get("cctu_id") or task.get("id"))
        sample = samples.get(cctu_id)
        if not sample:
            continue
        tools_raw = sample.get("tools")
        openai_tools = json.loads(tools_raw) if isinstance(tools_raw, str) else tools_raw
        if not isinstance(openai_tools, list):
            continue
        schema_by_name = {}
        for tool in openai_tools:
            name = tool_name_from_entry(tool)
            if name:
                schema_by_name[name] = tool_schema_from_entry(tool)
        mac_tools = task.get("tools")
        if not isinstance(mac_tools, list):
            continue
        task_changed = False
        for tool in mac_tools:
            if not isinstance(tool, dict):
                continue
            name = tool.get("name")
            if not isinstance(name, str) or name not in schema_by_name:
                continue
            new_schema = schema_by_name[name]
            if tool.get("input_schema") != new_schema:
                tool["input_schema"] = json.loads(json.dumps(new_schema))
                task_changed = True
        if task_changed:
            changed += 1

    mac_tasks.write_text(json.dumps(payload, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    return {"changed_tasks": changed, "path": str(mac_tasks)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-data", type=Path, default=DEFAULT_INPUT_DATA)
    parser.add_argument("--mac-tasks", type=Path, default=DEFAULT_MAC_TASKS)
    parser.add_argument("--skip-mac-sync", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = repair_input_data(args.input_data)
    print(f"Repaired input_data: {result['changed_tasks']} tasks")
    for note in result["notes"][:40]:
        print(f"  {note}")
    if len(result["notes"]) > 40:
        print(f"  ... {len(result['notes']) - 40} more")
    if not args.skip_mac_sync:
        sync = sync_mac_task_schemas(input_data=args.input_data, mac_tasks=args.mac_tasks)
        print(f"Synced mac-cctu-tasks schemas: {sync['changed_tasks']} tasks")


if __name__ == "__main__":
    main()
