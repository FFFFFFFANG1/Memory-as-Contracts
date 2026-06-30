def evaluate(trace):
    final = (trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    allowed = 'historical_event_data_retriever'
    forbidden_used = [c.get('name') for c in calls if c.get('name') and c.get('name') != allowed]
    prefix_ok = final.lstrip().startswith('Archival Record:')
    if not final.strip() and not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No response or tool calls to evaluate.', 'evidence_refs': []}
    if forbidden_used:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used non-permitted tool(s): {sorted(set(forbidden_used))}.', 'evidence_refs': [{'type':'tool_calls','names':sorted(set(forbidden_used))}]}
    if not prefix_ok:
        return {'observed_followed': False, 'confidence': 'high', 'reason': "Final response is not prefixed with 'Archival Record:'.", 'evidence_refs': [{'type':'final_response_prefix','value':final[:40]}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': "Only historical_event_data_retriever used (if any) and response begins with 'Archival Record:'.", 'evidence_refs': [{'type':'final_response_prefix','value':final[:40]}]}
