def evaluate(trace):
    calls = trace.get('tool_calls') or []
    names = {c.get('name') for c in calls if c.get('name')}
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls found in trajectory.','evidence_refs':[]}
    if len(names) >= 2:
        return {'observed_followed': True, 'confidence':'high','reason': f'Distinct retrieval tools invoked: {sorted(names)}','evidence_refs': sorted(names)}
    return {'observed_followed': False, 'confidence':'high','reason': f'Only one distinct tool used: {sorted(names)}; cross-validation requires >=2 distinct retrieval tools.','evidence_refs': sorted(names)}
