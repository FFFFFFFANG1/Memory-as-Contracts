def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    # Detect depth values mentioned in final response (numbers with depth context or m/meters)
    has_depth = bool(re.search(r'(depth|deep|meters|metres|\bm\b)', final, re.I)) and bool(re.search(r'\d', final))
    if not has_depth:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No depth values detected in final response.', 'evidence_refs': []}
    tool_names = {c.get('name') for c in calls if c.get('name')}
    depth_related = {'ocean_depth_analyzer','geographical_feature_measurement','factual_data_retriever'}
    independent_used = tool_names & depth_related
    if len(independent_used) >= 2:
        return {'observed_followed': True, 'confidence':'medium', 'reason': f'Two independent tools used for cross-check: {sorted(independent_used)}', 'evidence_refs': sorted(independent_used)}
    return {'observed_followed': False, 'confidence':'medium', 'reason': f'Depth values present but fewer than two independent tools used: {sorted(independent_used)}', 'evidence_refs': sorted(tool_names)}
