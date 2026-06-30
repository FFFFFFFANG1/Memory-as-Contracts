def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    _count_historical_event_info_retriever = sum(1 for name in tool_names if name == 'historical_event_info_retriever')
    if _count_historical_event_info_retriever < 3:
        reasons.append('historical_event_info_retriever' + ' call count below 3')
    _count_species_counter = sum(1 for name in tool_names if name == 'species_counter')
    if _count_species_counter < 3:
        reasons.append('species_counter' + ' call count below 3')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
