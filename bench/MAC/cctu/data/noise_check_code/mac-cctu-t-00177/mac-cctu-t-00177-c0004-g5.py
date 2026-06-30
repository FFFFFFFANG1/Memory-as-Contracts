import json
import re

SPEC = {'tool_usage': {'required_tools': ['exploration_history_finder'], 'forbidden_tools': []}}


def _word_count(text):
    return len(re.findall(r"\S+", text or ""))


def _contains_json_object(text):
    text = (text or "").strip()
    candidates = [text]
    candidates.extend(re.findall(r"\{.*?\}", text, flags=re.DOTALL))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def evaluate(trace):
    trace = trace or {}
    final = str(trace.get("final_response") or "")
    trajectory = trace.get("trajectory") or []
    tool_calls = trace.get("tool_calls") or []
    failures = []
    evidence = []

    if not final.strip() and not tool_calls:
        return {"observed_followed": False, "confidence": "high", "reason": "no observable behavior", "evidence_refs": []}

    length = SPEC.get("length") or {}
    if length:
        unit = length.get("unit") or "words"
        count = len(final) if unit == "characters" else _word_count(final)
        min_value = length.get("min")
        max_value = length.get("max")
        if isinstance(min_value, int) and count < min_value:
            failures.append(f"{unit} length {count} below minimum {min_value}")
        if isinstance(max_value, int) and count > max_value:
            failures.append(f"{unit} length {count} above maximum {max_value}")
        evidence.append({"field": "final_response", "unit": unit, "count": count})

    paragraph_min = SPEC.get("paragraph_min")
    if isinstance(paragraph_min, int):
        paragraphs = [part for part in final.split("\n\n") if part.strip()]
        if len(paragraphs) < paragraph_min:
            failures.append(f"paragraph count {len(paragraphs)} below minimum {paragraph_min}")

    paragraph_max = SPEC.get("paragraph_max")
    if isinstance(paragraph_max, int):
        paragraphs = [part for part in final.split("\n\n") if part.strip()]
        if len(paragraphs) > paragraph_max:
            failures.append(f"paragraph count {len(paragraphs)} above maximum {paragraph_max}")

    sentence_max = SPEC.get("sentence_max")
    if isinstance(sentence_max, int) and final.strip():
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", final.strip()) if part.strip()]
        if not sentences:
            sentences = [final.strip()]
        if len(sentences) > sentence_max:
            failures.append(f"sentence count {len(sentences)} above maximum {sentence_max}")

    if SPEC.get("json_object"):
        parsed = _contains_json_object(final)
        if parsed is None:
            failures.append("expected a valid JSON object")
        else:
            keys = set(str(key) for key in parsed.keys())
            required_any = set(str(key) for key in SPEC.get("json_keys_any") or [])
            if required_any and not required_any.intersection(keys):
                failures.append(f"JSON object missing expected key candidates {sorted(required_any)}")
            only_keys = set(str(key) for key in SPEC.get("json_only_keys") or [])
            if only_keys and keys != only_keys:
                failures.append(f"JSON object keys {sorted(keys)} do not match required keys {sorted(only_keys)}")
            evidence.append({"field": "final_response", "json_keys": sorted(keys)})

    for term in SPEC.get("contains_terms") or []:
        if str(term).lower() not in final.lower():
            failures.append(f"missing term {term!r}")

    if SPEC.get("requires_bold") and not re.search(r"\*\*[^*]+\*\*|__[^_]+__", final):
        failures.append("expected bold markdown text")

    for check in SPEC.get("response_checks") or []:
        name = check.get("name")
        if name in {"plain_text", "no_markdown"}:
            marks = ("**", "__", "# ", "- ", "* ", "`")
            if any(mark in final for mark in marks):
                failures.append("markdown or special formatting present")
            try:
                parsed = json.loads(final.strip())
                if isinstance(parsed, dict):
                    failures.append("json object present in plain text response")
            except Exception:
                pass
        elif name == "markdown_any":
            marks = ("**", "__", "# ")
            if not any(mark in final for mark in marks):
                failures.append("markdown marker missing")
        elif name == "date_format":
            fmt = str(check.get("format") or "any")
            if fmt == "iso":
                pattern = r"\b\d{4}-\d{2}-\d{2}\b"
            else:
                pattern = r"\b\d{4}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b"
            if not re.search(pattern, final, flags=re.IGNORECASE):
                failures.append("expected date in response")
        elif name == "ends_with":
            value = str(check.get("value") or "")
            if value and not final.rstrip().endswith(value):
                failures.append(f"response does not end with {value!r}")
        elif name == "no_trailing_punctuation":
            if final.rstrip() and final.rstrip()[-1] in ".!?,;:":
                failures.append("trailing punctuation present")
        elif name == "starts_with":
            value = str(check.get("value") or "")
            if value and not final.startswith(value):
                failures.append(f"response does not start with {value!r}")
        elif name == "contains_terms":
            for term in check.get("terms") or []:
                if str(term).lower() not in final.lower():
                    failures.append(f"missing term {term!r}")
        elif name == "excludes_terms":
            for term in check.get("terms") or []:
                if str(term) in final:
                    failures.append(f"forbidden term present {term!r}")

    rounds = SPEC.get("interaction_rounds") or {}
    if rounds:
        count = len(trajectory)
        min_value = rounds.get("min")
        max_value = rounds.get("max")
        if isinstance(min_value, int) and count < min_value:
            failures.append(f"interaction rounds {count} below minimum {min_value}")
        if isinstance(max_value, int) and count > max_value:
            failures.append(f"interaction rounds {count} above maximum {max_value}")

    tool_count_spec = SPEC.get("tool_call_count") or {}
    if tool_count_spec:
        count = len(tool_calls)
        min_value = tool_count_spec.get("min")
        max_value = tool_count_spec.get("max")
        if isinstance(min_value, int) and count < min_value:
            failures.append(f"tool calls {count} below minimum {min_value}")
        if isinstance(max_value, int) and count > max_value:
            failures.append(f"tool calls {count} above maximum {max_value}")

    per_tool = SPEC.get("specific_tool_call_count") or {}
    if per_tool:
        counts = {}
        for call in tool_calls:
            name = str(call.get("name") or "")
            counts[name] = counts.get(name, 0) + 1
        for tool, bounds in per_tool.items():
            count = counts.get(str(tool), 0)
            min_value = bounds.get("min") if isinstance(bounds, dict) else None
            max_value = bounds.get("max") if isinstance(bounds, dict) else None
            if isinstance(min_value, int) and count < min_value:
                failures.append(f"{tool} calls {count} below minimum {min_value}")
            if isinstance(max_value, int) and count > max_value:
                failures.append(f"{tool} calls {count} above maximum {max_value}")

    tool_usage = SPEC.get("tool_usage") or {}
    if tool_usage:
        called = {str(call.get("name") or "") for call in tool_calls if call.get("name")}
        required_tools = [str(item) for item in tool_usage.get("required_tools") or [] if str(item)]
        forbidden_tools = [str(item) for item in tool_usage.get("forbidden_tools") or [] if str(item)]
        missing = sorted(tool for tool in required_tools if tool not in called)
        if missing:
            failures.append("required tools not called: " + ", ".join(missing[:5]))
        forbidden_used = sorted(tool for tool in forbidden_tools if tool in called)
        if forbidden_used:
            failures.append("forbidden tools called: " + ", ".join(forbidden_used[:5]))

    if SPEC.get("require_tool_calls") and not tool_calls:
        failures.append("no tool calls observed")

    if SPEC.get("forbid_tool_calls") and tool_calls:
        failures.append("tool calls are forbidden by constraint")

    allowed_only = [str(item) for item in SPEC.get("allowed_tools_only") or [] if str(item)]
    if allowed_only:
        called = {str(call.get("name") or "") for call in tool_calls if call.get("name")}
        disallowed = sorted(name for name in called if name and name not in set(allowed_only))
        if disallowed:
            failures.append("tools outside allowed set: " + ", ".join(disallowed[:5]))

    groups = SPEC.get("tool_parallel") or []
    if groups:
        step_sets = []
        for step in trajectory:
            step_sets.append({str(call.get("name") or "") for call in step.get("tool_calls") or [] if isinstance(call, dict)})
        for group in groups:
            expected = {str(item) for item in group if item}
            if expected and not any(expected <= names for names in step_sets):
                failures.append(f"tool group not called in same step: {sorted(expected)}")

    if not final and not tool_calls and any(
        key in SPEC
        for key in ("length", "json_object", "response_checks", "contains_terms", "requires_bold")
    ):
        return {"observed_followed": None, "confidence": "unknown", "reason": "missing final response", "evidence_refs": evidence}
    if failures:
        return {"observed_followed": False, "confidence": "medium", "reason": "; ".join(failures[:8]), "evidence_refs": evidence}
    return {"observed_followed": True, "confidence": "medium", "reason": "rule-based spec repair checks passed", "evidence_refs": evidence}
