def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No tool calls; cannot cross-verify against 3 independent outputs.', 'evidence_refs': []}
    names = [c.get('name') for c in calls if c.get('name')]
    distinct = set(names)
    final = (trace.get('final_response') or '').strip()
    if len(calls) < 3 or len(distinct) < 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {len(calls)} tool calls across {len(distinct)} distinct tools; need >=3 independent outputs per fact.', 'evidence_refs': list(distinct)}
    if not final:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Sufficient tool calls but no final lineage to inspect.', 'evidence_refs': list(distinct)}
    return {'observed_followed': None, 'confidence': 'low', 'reason': f'{len(calls)} calls across {len(distinct)} tools present; cannot semantically confirm each recorded fact was cross-verified.', 'evidence_refs': list(distinct)}
