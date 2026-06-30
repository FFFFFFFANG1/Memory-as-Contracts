def evaluate(trace):
    historical_tools = {
        'historical_event_finder','historical_event_finder_merged',
        'historical_event_information_tool','disaster_event_info_retriever',
        'aviation_incident_database','mountaineering_event_finder_v2',
        'historical_organization_info_retriever'
    }
    calls = trace.get('tool_calls') or []
    used = set()
    for c in calls:
        n = c.get('name')
        if n in historical_tools:
            used.add(n)
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls in trace', 'evidence_refs': []}
    if len(used) >= 2:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'cross-verified via {sorted(used)}', 'evidence_refs': sorted(used)}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'only {len(used)} independent historical tool(s) used: {sorted(used)}', 'evidence_refs': sorted(used)}
