def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    allowed_tools = set(['altitude_finder', 'bird_characteristic_finder', 'car_design_influence_finder', 'car_specification_retriever', 'event_locator', 'historical_artisan_finder', 'historical_site_finder', 'museum_exhibit_locator'])
    forbidden_used = sorted({name for name in tool_names if name and name not in allowed_tools})
    if forbidden_used:
        reasons.append('forbidden tools used: ' + ', '.join(forbidden_used[:5]))
    round_count = len(trajectory)
    if round_count > 16:
        reasons.append('interaction rounds {round_count} above 16')
    if 'eu' not in response.lower():
        reasons.append('eu' + ' not mentioned in response')
    if 'un' not in response.lower():
        reasons.append('un' + ' not mentioned in response')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
