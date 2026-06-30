def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to verify against.', 'evidence_refs': []}
    low = final.lower()
    tool_names = []
    seen = set()
    for c in calls:
        n = (c.get('name') or '').strip()
        if n and n not in seen:
            seen.add(n); tool_names.append(n)
    missing_tools = [n for n in tool_names if n.lower() not in low]
    # Look for index references like 'call 1', 'index 2', '#3', '[1]', 'call index 0'
    idx_pattern = re.compile(r'(call\s*(index)?\s*#?\d+|index\s*[:#]?\s*\d+|#\d+|\[\d+\])', re.I)
    idx_hits = idx_pattern.findall(final)
    has_indices = len(idx_hits) >= max(1, min(len(calls), 1))
    if missing_tools:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Final response does not mention tool(s): {missing_tools}', 'evidence_refs': []}
    if not has_indices:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No call index references found in final response.', 'evidence_refs': []}
    # Heuristic: facts should be listed; check for list-like structure or multiple lines
    lines = [l for l in final.splitlines() if l.strip()]
    listed = len(lines) >= 2 or bool(re.search(r'(^|\n)\s*[-*\d\.]', final))
    if not listed:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'Facts do not appear to be listed alongside tool/index.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Final response references all used tool names and includes call index notation.', 'evidence_refs': []}
