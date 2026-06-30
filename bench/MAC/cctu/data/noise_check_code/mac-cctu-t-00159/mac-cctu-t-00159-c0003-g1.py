def evaluate(trace):
    traj = trace.get('trajectory') or []
    relevant_turns = []
    violations = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        names = [tc.get('name') or (tc.get('function') or {}).get('name') for tc in tcs]
        if any(n == 'natural_feature_locator' for n in names):
            relevant_turns.append(i)
            if len(tcs) > 1:
                violations.append({'turn': i, 'tools': names})
    if not relevant_turns:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No natural feature scoping turns found.', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Natural feature scoping turn(s) had multiple tool calls: {violations}', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {len(relevant_turns)} natural feature scoping turn(s) used a single tool invocation.', 'evidence_refs': relevant_turns}
