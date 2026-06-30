def evaluate(trace):
    locators = {'business_locator','commercial_district_locator','landmark_city_locator','mall_management_locator','park_feature_locator','urban_feature_locator'}
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory.', 'evidence_refs': []}
    bio_seen = False
    for i, c in enumerate(calls):
        name = c.get('name')
        if name == 'biographical_info_retriever':
            bio_seen = True
            continue
        if name in locators and not bio_seen:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'Locator tool {name!r} invoked at index {i} before any biographical_info_retriever call.', 'evidence_refs': [{'tool_index': i, 'tool': name}]}
    used_locator = any(c.get('name') in locators for c in calls)
    if not used_locator and not bio_seen:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No locator tools and no biographical retriever used; constraint not exercised.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'All locator tool invocations are preceded by biographical_info_retriever.', 'evidence_refs': []}
