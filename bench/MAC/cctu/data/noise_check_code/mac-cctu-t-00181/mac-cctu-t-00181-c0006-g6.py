def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found.', 'evidence_refs': []}
    allowed_initial = {'city_feature_finder', 'honor_locator'}
    later_lookups = {'musical_composition_finder', 'philosopher_work_locator', 'historical_works_identifier'}
    initial_names = []
    violation = None
    for c in calls:
        name = c.get('name')
        initial_names.append(name)
        if name in later_lookups:
            break
        if name not in allowed_initial:
            violation = name
            break
    if violation is not None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Initial tool call {violation!r} is not limited to city_feature_finder/honor_locator before any composition/philosophy lookup. Sequence so far: {initial_names}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'Initial calls restricted to allowed set before composition/philosophy lookups. Sequence: {initial_names}', 'evidence_refs': []}
