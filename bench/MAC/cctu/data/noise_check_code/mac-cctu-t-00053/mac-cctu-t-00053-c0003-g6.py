def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    count = sum(1 for c in tool_calls if (c.get('name') or '') == 'historical_population_retriever')
    final = trace.get('final_response') or ''
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Look for YAML block
    yaml_block = None
    m = re.search(r'```(?:yaml|yml)?\s*\n(.*?)```', final, re.DOTALL|re.IGNORECASE)
    if m:
        yaml_block = m.group(1)
    else:
        yaml_block = final
    # Detect top-level keys that look like census years (4-digit year at start of line followed by colon)
    year_keys = re.findall(r'(?m)^\s*(1[6-9]\d{2}|20\d{2})\s*:', yaml_block)
    has_yaml_year_keys = len(year_keys) >= 1
    enough_calls = count >= 3
    followed = enough_calls and has_yaml_year_keys
    reason = f'historical_population_retriever calls={count} (need>=3); yaml year keys found={year_keys}'
    return {'observed_followed': bool(followed), 'confidence': 'high' if (enough_calls and has_yaml_year_keys) or (not enough_calls) else 'medium', 'reason': reason, 'evidence_refs': []}
