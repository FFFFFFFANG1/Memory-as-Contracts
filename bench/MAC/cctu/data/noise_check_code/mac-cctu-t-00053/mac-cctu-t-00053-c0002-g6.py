def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    names = [c.get('name') for c in calls]
    has_city = 'location_city_identifier' in names
    has_district = 'district_identifier' in names
    total = len(calls)
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls recorded', 'evidence_refs': []}
    if not (has_city and has_district):
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'missing required tools; city={has_city}, district={has_district}', 'evidence_refs': names}
    if total < 5:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'only {total} tool calls; need >=5 per site', 'evidence_refs': names}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'both required tools present and {total} calls made', 'evidence_refs': names}
