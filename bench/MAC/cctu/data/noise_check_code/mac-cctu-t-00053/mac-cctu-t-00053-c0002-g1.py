def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found.', 'evidence_refs': []}
    geo_tz = {'beach_locator','district_identifier','location_city_identifier','timezone_finder'}
    # Find first historical_event_locator call index
    hist_idx = next((i for i,c in enumerate(calls) if c.get('name')=='historical_event_locator'), None)
    if hist_idx is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'historical_event_locator was never used to draft the preliminary event summary.', 'evidence_refs': [c.get('name') for c in calls]}
    # Check no geo/timezone tool appears before the first historical_event_locator call
    early = calls[:hist_idx]
    violators = [(i,c.get('name')) for i,c in enumerate(early) if c.get('name') in geo_tz]
    if violators:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Geographic/timezone tool(s) invoked before historical_event_locator during preliminary framing: {violators}', 'evidence_refs': [v[1] for v in violators]}
    # Also check: the very first call should be historical_event_locator (preliminary framing)
    first_name = calls[0].get('name')
    if first_name != 'historical_event_locator':
        # if first call is some other non-geo tool, still likely violates 'rely exclusively' rule
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Preliminary fact framing did not rely exclusively on historical_event_locator; first tool was {first_name}.', 'evidence_refs': [first_name]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'historical_event_locator was used first with no geographic/timezone tools invoked before it.', 'evidence_refs': [c.get('name') for c in calls[:hist_idx+1]]}
