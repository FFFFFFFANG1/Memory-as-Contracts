def evaluate(trace):
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls]
    total = len(names)
    ef_idx = None
    ni_idx = None
    for i, n in enumerate(names):
        if n == 'exhibition_finder' and ef_idx is None:
            ef_idx = i
        if n == 'neighborhood_identifier' and ni_idx is None:
            ni_idx = i
    if total > 7:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Total tool calls {total} exceeds 7', 'evidence_refs': []}
    if ni_idx is not None and ef_idx is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'neighborhood_identifier called without prior exhibition_finder', 'evidence_refs': []}
    if ni_idx is not None and ef_idx is not None and ef_idx > ni_idx:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'exhibition_finder called after neighborhood_identifier', 'evidence_refs': []}
    if ef_idx is None and ni_idx is None:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Neither tool invoked; ordering not exercised', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Ordering respected and within 7 calls', 'evidence_refs': []}
