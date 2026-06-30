def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    gated = {'residence_locator', 'event_location_identifier'}
    anchor = 'exploration_history_finder'
    relevant = [c for c in calls if (c.get('name') in gated or c.get('name') == anchor)]
    if not any(c.get('name') in gated for c in relevant):
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No residence_locator or event_location_identifier calls present', 'evidence_refs': []}
    seen_anchor = False
    for c in calls:
        n = c.get('name')
        if n == anchor:
            seen_anchor = True
        elif n in gated and not seen_anchor:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'{n} called before any exploration_history_finder', 'evidence_refs': [c.get('index')]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'exploration_history_finder preceded all gated calls', 'evidence_refs': []}
