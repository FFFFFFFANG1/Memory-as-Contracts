def evaluate(trace):
    calls = trace.get('tool_calls') or []
    arithmetic = {'digit_sum_calculator','enhanced_arithmetic_calculator'}
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    hist_seen = False
    arith_indices = []
    for c in calls:
        name = c.get('name')
        idx = c.get('index')
        if name == 'historical_data_retriever':
            if not arith_indices:
                hist_seen = True
        if name in arithmetic:
            if not hist_seen:
                return {'observed_followed': False, 'confidence': 'high', 'reason': f'arithmetic tool {name} called at index {idx} before historical_data_retriever', 'evidence_refs': [{'index': idx, 'name': name}]}
    if not any(c.get('name') in arithmetic for c in calls):
        if hist_seen:
            return {'observed_followed': True, 'confidence': 'medium', 'reason': 'no arithmetic aggregation tools used; constraint vacuously satisfied', 'evidence_refs': []}
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'no arithmetic aggregation tools used', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'historical_data_retriever was invoked before all arithmetic aggregation tool calls', 'evidence_refs': []}
