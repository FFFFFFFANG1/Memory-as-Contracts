def evaluate(trace):
    political_tools = {'election_result_finder','political_event_finder','political_event_search','political_event_tracker','political_appointment_finder'}
    other_political = political_tools - {'political_appointment_finder'}
    calls = trace.get('tool_calls') or []
    paf_idx = None
    first_other_idx = None
    for i, c in enumerate(calls):
        name = c.get('name')
        if name == 'political_appointment_finder' and paf_idx is None:
            paf_idx = i
        elif name in other_political and first_other_idx is None:
            first_other_idx = i
    if first_other_idx is None and paf_idx is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No political-event tools were called.', 'evidence_refs': []}
    if first_other_idx is None:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Only political_appointment_finder used among political-event tools.', 'evidence_refs': [{'tool_call_index': paf_idx}]}
    if paf_idx is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Another political-event tool was used without political_appointment_finder being called.', 'evidence_refs': [{'tool_call_index': first_other_idx}]}
    if paf_idx < first_other_idx:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'political_appointment_finder was called before other political-event tools.', 'evidence_refs': [{'tool_call_index': paf_idx},{'tool_call_index': first_other_idx}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'political_appointment_finder was called after another political-event tool.', 'evidence_refs': [{'tool_call_index': paf_idx},{'tool_call_index': first_other_idx}]}
