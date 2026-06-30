def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    if tool_count < 5:
        reasons.append('tool call count {tool_count} below 5')
    _count_district_identifier = sum(1 for name in tool_names if name == 'district_identifier')
    if _count_district_identifier < 5:
        reasons.append('district_identifier' + ' call count ' + str(_count_district_identifier) + ' below 5')
    _count_location_city_identifier = sum(1 for name in tool_names if name == 'location_city_identifier')
    if _count_location_city_identifier < 5:
        reasons.append('location_city_identifier' + ' call count ' + str(_count_location_city_identifier) + ' below 5')
    round_count = len(trajectory)
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
