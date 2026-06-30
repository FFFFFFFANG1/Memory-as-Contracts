def evaluate(trace):
    traj = trace.get('trajectory') or []
    found = False
    violations = []
    for i, step in enumerate(traj):
        calls = step.get('tool_calls') or []
        names = [ (c.get('name') or c.get('tool_name') or '') for c in calls ]
        for idx, n in enumerate(names):
            if n == 'nearby_reserve_locator':
                found = True
                after = names[idx+1:]
                if 'park_feature_locator' not in after:
                    violations.append({'turn': i, 'call_index': idx})
    if not found:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'nearby_reserve_locator not used', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'nearby_reserve_locator not followed by park_feature_locator in same turn: {violations}', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Each nearby_reserve_locator call followed by park_feature_locator in same turn', 'evidence_refs': []}
