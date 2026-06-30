def evaluate(trace):
    tool_calls = trace.get('tool_calls', []) or []
    hist = 'historical_financial_data_retriever'
    dis = 'disaster_data_retriever'
    used_hist = any(tc.get('name') == hist for tc in tool_calls)
    used_dis = any(tc.get('name') == dis for tc in tool_calls)
    if not used_hist and not used_dis:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Neither tool was invoked.', 'evidence_refs': []}
    # Check that they are not in the same parallel step (same iteration)
    iterations = {}
    for tc in tool_calls:
        it = tc.get('iteration')
        iterations.setdefault(it, set()).add(tc.get('name'))
    for it, names in iterations.items():
        if hist in names and dis in names:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'Both historical_financial_data_retriever and disaster_data_retriever called in same step (iteration {it}).', 'evidence_refs': [str(it)]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'historical_financial_data_retriever not combined with disaster_data_retriever in same step.', 'evidence_refs': []}
