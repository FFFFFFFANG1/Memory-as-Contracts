def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trace.', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    refs = [{'index': c.get('index'), 'name': c.get('name')} for c in calls]
    first = names[0]
    if first != 'historical_infrastructure_locator':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool was {first!r}, expected historical_infrastructure_locator.', 'evidence_refs': refs[:1]}
    hist_indices = [i for i, n in enumerate(names) if n == 'historical_infrastructure_locator']
    pop_indices = [i for i, n in enumerate(names) if n == 'population_data_retriever']
    for pi in pop_indices:
        prior_hist = [hi for hi in hist_indices if hi < pi]
        if not prior_hist:
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'population_data_retriever called without a prior historical_infrastructure_locator call to verify.', 'evidence_refs': [refs[pi]]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'historical_infrastructure_locator invoked first; population_data_retriever only used after it.', 'evidence_refs': refs}
