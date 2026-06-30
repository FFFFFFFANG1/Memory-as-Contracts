def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').strip()
    calls = trace.get('tool_calls') or []
    tools = {c.get('name') for c in calls if c.get('name')}
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    distinct_ok = len(tools) >= 2
    # Check for semicolon usage and absence of period-terminated clauses
    has_semicolon = ';' in final
    # Strip trailing whitespace; check if it ends with period
    stripped = final.rstrip()
    ends_with_period = stripped.endswith('.')
    # Count sentence-ending periods (not in abbreviations or decimals)
    period_sentences = re.findall(r'[A-Za-z0-9\)\"]\.(\s|$)', stripped)
    period_terminated = ends_with_period or len(period_sentences) > 0
    semicolon_style_ok = has_semicolon and not period_terminated
    followed = distinct_ok and semicolon_style_ok
    reason = f'distinct_tools={len(tools)}, has_semicolon={has_semicolon}, period_terminated={period_terminated}'
    return {'observed_followed': bool(followed), 'confidence': 'high' if (distinct_ok or len(tools)==0) else 'medium', 'reason': reason, 'evidence_refs': [{'tools': sorted(list(tools))}]}
