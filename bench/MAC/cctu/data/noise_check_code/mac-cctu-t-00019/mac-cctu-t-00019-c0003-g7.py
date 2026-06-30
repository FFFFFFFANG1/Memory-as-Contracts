def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    names = [c.get('name','') for c in calls]
    verifiers = {'historical_event_analyzer','event_location_finder','historical_event_data_retriever','historical_event_locator','aviation_incident_locator'}
    primary_set = set(names) - verifiers
    used_verifiers = [n for n in names if n in verifiers]
    distinct_tools = set(names)
    if len(distinct_tools) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only one tool used: {list(distinct_tools)}; no cross-check performed', 'evidence_refs': names}
    if not used_verifiers:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No secondary verification tool (e.g., historical_event_analyzer or event_location_finder) was invoked', 'evidence_refs': names}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Multiple tools used including verifier(s): {used_verifiers}', 'evidence_refs': names}
