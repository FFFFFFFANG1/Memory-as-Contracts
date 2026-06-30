def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    geo_tools = {'landmark_city_locator', 'bridge_identifier', 'event_locator', 'infrastructure_info_retriever'}
    # Group calls by iteration as a proxy for sub-query
    by_iter = {}
    for tc in tool_calls:
        it = tc.get('iteration', 0)
        by_iter.setdefault(it, []).append(tc)
    violations = []
    checked = 0
    for it, calls in sorted(by_iter.items()):
        calls_sorted = sorted(calls, key=lambda c: c.get('index', 0))
        names = [c.get('name') for c in calls_sorted]
        if not any(n in geo_tools or n == 'supply_chain_tracker' for n in names):
            continue
        checked += 1
        if names[0] != 'supply_chain_tracker':
            violations.append({'iteration': it, 'first_tool': names[0], 'sequence': names})
    if checked == 0:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No sub-query with relevant tools detected', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(violations)} sub-query group(s) did not start with supply_chain_tracker', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'All sub-query groups start with supply_chain_tracker before geospatial lookups', 'evidence_refs': []}
