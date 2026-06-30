def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls to log', 'evidence_refs': []}
    low = final.lower()
    has_log_header = any(k in low for k in ['chain of custody','chain-of-custody','custody log','custody chain'])
    if not has_log_header:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no chain-of-custody log section found', 'evidence_refs': []}
    tool_names = []
    for tc in tool_calls:
        n = tc.get('name')
        if n and n not in tool_names:
            tool_names.append(n)
    idx = low.find('custody')
    log_section = final[idx:] if idx >= 0 else final
    log_low = log_section.lower()
    missing = [n for n in tool_names if n.lower() not in log_low]
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'log missing tool calls: {missing}', 'evidence_refs': []}
    # check log appears before/at end (appended). Heuristic: log header position should be in latter half or final id appears earlier.
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'chain-of-custody log present and lists all supplier tool calls', 'evidence_refs': [n for n in tool_names]}
