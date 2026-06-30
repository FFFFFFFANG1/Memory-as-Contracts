def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    violations = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if not tcs:
            continue
        names = set()
        for tc in tcs:
            n = tc.get('name') or (tc.get('function') or {}).get('name')
            if n:
                names.add(n)
        if len(names) > 2:
            violations.append({'turn': i, 'unique_tools': sorted(names)})
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(violations)} turn(s) exceeded 2 unique tool types', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'each turn used <=2 unique tool types', 'evidence_refs': []}
