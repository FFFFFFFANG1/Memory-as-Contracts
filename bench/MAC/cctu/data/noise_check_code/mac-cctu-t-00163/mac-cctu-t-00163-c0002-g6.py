def evaluate(trace):
    tools = {'historical_maritime_event_finder','water_body_info_retriever'}
    calls = [c for c in trace.get('tool_calls',[]) if c.get('name') in tools]
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No relevant tool calls found', 'evidence_refs': []}
    iters = {c.get('iteration') for c in calls}
    if len(iters) == 1 and len(calls) >= 2:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {len(calls)} relevant calls in single iteration {iters}', 'evidence_refs': list(iters)}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'Relevant calls split across iterations {iters}', 'evidence_refs': list(iters)}
