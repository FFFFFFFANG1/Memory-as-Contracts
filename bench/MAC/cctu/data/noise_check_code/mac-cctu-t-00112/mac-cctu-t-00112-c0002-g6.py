def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls present.', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    first_ok = names[0] == 'earthquake_data_retriever'
    eq_idx = next((i for i,n in enumerate(names) if n == 'earthquake_data_retriever'), -1)
    hi_idx = next((i for i,n in enumerate(names) if n == 'historical_incident_data_retriever'), -1)
    if eq_idx == -1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'earthquake_data_retriever not used as first tool of choice.', 'evidence_refs': [{'tool_sequence': names}]}
    if not first_ok:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool was {names[0]}, not earthquake_data_retriever.', 'evidence_refs': [{'tool_sequence': names}]}
    if hi_idx == -1 or hi_idx < eq_idx:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'historical_incident_data_retriever was not used to cross-check after earthquake_data_retriever.', 'evidence_refs': [{'tool_sequence': names}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'earthquake_data_retriever called first and historical_incident_data_retriever used afterwards for cross-check.', 'evidence_refs': [{'tool_sequence': names}]}
