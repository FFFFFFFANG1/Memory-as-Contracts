def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    names = [c.get('name','') for c in calls]
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed.', 'evidence_refs': []}
    tz_calls = [i for i,n in enumerate(names) if n == 'timezone_finder']
    has_beach = 'beach_locator' in names
    has_district = 'district_identifier' in names
    if tz_calls and not has_beach:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'timezone_finder used without beach_locator coastal context.', 'evidence_refs': [{'tool_call_indices': tz_calls}]}
    geo_like = {'location_city_identifier'}
    misused = [i for i,n in enumerate(names) if n in geo_like and not (has_beach or has_district)]
    if misused:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'Geographic lookup performed without beach_locator/district_identifier as primary.', 'evidence_refs': [{'tool_call_indices': misused}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'beach_locator/district_identifier used as primary; timezone_finder usage consistent with coastal annotation.', 'evidence_refs': []}
