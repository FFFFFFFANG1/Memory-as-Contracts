def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    names = [c.get('name','') for c in calls]
    primary = 'award_information_and_record_retriever'
    used_primary = primary in names
    other_sources = [n for n in names if n and n != primary]
    if not used_primary:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Primary award_information_and_record_retriever not used', 'evidence_refs': names}
    if not other_sources:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No second source used for cross-verification', 'evidence_refs': names}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Primary award tool used and at least one additional tool present for cross-verification', 'evidence_refs': names}
