def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trace.', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    primary = 'sports_event_winner_finder'
    if primary not in names:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Primary tool sports_event_winner_finder was not used.', 'evidence_refs': [{'tools_used': sorted(set(names))}]}
    # find first index of primary; verification calls should accompany
    others = [n for n in names if n != primary]
    distinct_others = sorted(set(others))
    if len(distinct_others) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Need at least two independent retrieval tools for cross-verification; found {len(distinct_others)}: {distinct_others}.', 'evidence_refs': [{'tools_used': sorted(set(names))}]}
    # Check primary appears before or alongside verifications (primary-source role)
    first_primary = names.index(primary)
    verifications_after = [i for i,n in enumerate(names) if n != primary and i >= first_primary]
    if len(set(names[i] for i in verifications_after)) < 2:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Primary used but independent verification tools did not clearly follow primary retrieval.', 'evidence_refs': [{'sequence': names}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Primary tool used and {len(distinct_others)} distinct verification tools present: {distinct_others}.', 'evidence_refs': [{'sequence': names}]}
