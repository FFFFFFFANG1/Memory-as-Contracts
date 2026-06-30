def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    aviation_used = any((tc.get('name') or '') == 'aviation_incident_database' for tc in tcs)
    if not aviation_used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no aviation incident lookup detected', 'evidence_refs': []}
    distinct = set()
    for tc in tcs:
        name = tc.get('name') or ''
        if name:
            distinct.add(name)
    # require at least 2 distinct tools used overall (cross-reference)
    if len(distinct) >= 2:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'cross-referenced {len(distinct)} distinct tools: {sorted(distinct)}', 'evidence_refs': sorted(distinct)}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'only one tool used: {sorted(distinct)}', 'evidence_refs': sorted(distinct)}
