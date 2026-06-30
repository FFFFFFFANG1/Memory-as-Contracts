def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    called = {name for name in tool_names if name}
    required_tools = ['political_event_tracker']
    missing = sorted(t for t in required_tools if t not in called)
    if missing:
        reasons.append('required tools not called: ' + ', '.join(missing[:5]))
    forbidden_tools = ['event_location_finder', 'historical_event_finder', 'historical_event_locator', 'hurricane_data_analyzer', 'incident_info_retriever', 'legal_case_search']
    forbidden_used = sorted(t for t in forbidden_tools if t in called)
    if forbidden_used:
        reasons.append('forbidden tools called: ' + ', '.join(forbidden_used[:5]))
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
