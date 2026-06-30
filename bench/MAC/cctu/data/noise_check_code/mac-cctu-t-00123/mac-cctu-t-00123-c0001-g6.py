def evaluate(trace):
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls]
    pop_calls = [i for i,n in enumerate(names) if n=='population_data_retriever']
    if not pop_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'population_data_retriever not used', 'evidence_refs': []}
    secondary = [n for n in names if n and n!='population_data_retriever']
    if not secondary:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'population_data_retriever used without any secondary tool for cross-validation', 'evidence_refs': [{'tool_indices': pop_calls}]}
    final = (trace.get('final_response') or '')
    # Require at least one secondary call to occur before the final response (i.e., exists in trajectory)
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'secondary tools present: {sorted(set(secondary))}', 'evidence_refs': [{'secondary_tools': sorted(set(secondary))}]}
