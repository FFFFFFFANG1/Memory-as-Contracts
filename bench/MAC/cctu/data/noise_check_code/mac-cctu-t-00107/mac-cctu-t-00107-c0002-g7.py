def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    specialized = {'aviation_incident_info_data_retriever','historical_event_finder'}
    primary = 'historical_event_retriever'
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed.', 'evidence_refs': []}
    first_primary_idx = None
    first_specialized_idx = None
    refs = []
    for i, c in enumerate(calls):
        name = c.get('name')
        if name == primary and first_primary_idx is None:
            first_primary_idx = i
            refs.append({'index': c.get('index', i), 'name': name})
        if name in specialized and first_specialized_idx is None:
            first_specialized_idx = i
            refs.append({'index': c.get('index', i), 'name': name})
    if first_specialized_idx is None and first_primary_idx is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Neither primary nor specialized disaster tools were invoked.', 'evidence_refs': []}
    if first_specialized_idx is None:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Primary historical_event_retriever was used; no specialized DB fallback needed.', 'evidence_refs': refs}
    if first_primary_idx is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Specialized DB was called without consulting historical_event_retriever first.', 'evidence_refs': refs}
    if first_primary_idx < first_specialized_idx:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'historical_event_retriever consulted before specialized DB.', 'evidence_refs': refs}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'Specialized DB invoked before historical_event_retriever.', 'evidence_refs': refs}
