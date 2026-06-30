def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls; multi-hop precondition not observed', 'evidence_refs': []}
    names = [str((c.get('name') or c.get('tool_name') or '')).strip() for c in calls]
    names = [n for n in names if n]
    if len(names) < 2:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'single tool call; not a multi-hop lookup', 'evidence_refs': []}
    first = names[0]
    if first == 'location_identifier':
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'multi-hop sequence begins with location_identifier', 'evidence_refs': [{'first_tool': first, 'sequence': names}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'multi-hop sequence begins with {first!r}, not location_identifier', 'evidence_refs': [{'first_tool': first, 'sequence': names}]}
