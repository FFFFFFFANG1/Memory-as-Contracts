def evaluate(trace):
    retrievers = {'historical_event_data_retriever','historical_event_finder','historical_event_retriever','merged_historical_event_tool'}
    calls = trace.get('tool_calls') or []
    used = [c for c in calls if c.get('name') in retrievers]
    distinct = {c.get('name') for c in used}
    if not used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No retriever tool calls found in trajectory.', 'evidence_refs': []}
    if len(distinct) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only one distinct retriever used: {sorted(distinct)}; cannot cross-check figures across two retrievers.', 'evidence_refs': [c.get('index') for c in used]}
    final = (trace.get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Two distinct retrievers used but no final response to identify recorded figures.', 'evidence_refs': sorted(distinct)}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'At least two distinct retriever tools used ({sorted(distinct)}), consistent with cross-checking.', 'evidence_refs': sorted(distinct)}
