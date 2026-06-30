def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls but constraint requires specific tool ordering', 'evidence_refs': []}
    names = [str(c.get('name') or '') for c in calls]
    if names[0] != 'quarry_mineral_locator':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'first tool is {names[0]!r}, expected quarry_mineral_locator', 'evidence_refs': [{'index': 0, 'name': names[0]}]}
    if names[-1] != 'geographic_feature_locator':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'last tool is {names[-1]!r}, expected geographic_feature_locator', 'evidence_refs': [{'index': len(names)-1, 'name': names[-1]}]}
    middle = names[1:-1]
    if middle != sorted(middle):
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'intermediate tools not alphabetically ordered: {middle}', 'evidence_refs': [{'middle': middle, 'expected': sorted(middle)}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'first=quarry_mineral_locator, last=geographic_feature_locator, middle alphabetical', 'evidence_refs': [{'sequence': names}]}
