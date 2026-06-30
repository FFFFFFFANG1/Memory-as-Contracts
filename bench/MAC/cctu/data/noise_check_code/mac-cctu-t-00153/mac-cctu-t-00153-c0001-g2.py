def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls but constraint requires 6-10 tool calls', 'evidence_refs': []}
    total = len(tool_calls)
    reasons = []
    if total < 6 or total > 10:
        reasons.append('total tool calls ' + str(total) + ' not in [6,10]')
    limited = ['city_feature_identifier','city_reputation_identifier','artist_location_finder','artwork_valuation_tool','company_locator','financial_data_retriever']
    from collections import defaultdict
    counts = defaultdict(int)
    for c in tool_calls:
        n = str(c.get('name') or '')
        if n:
            counts[n] += 1
    for t in limited:
        if counts[t] > 2:
            reasons.append(t + ' called ' + str(counts[t]) + ' times (>2)')
    # group calls by iteration/step to check parallel invocation
    steps = defaultdict(list)
    has_iter = False
    for c in tool_calls:
        it = c.get('iteration')
        if it is not None:
            has_iter = True
            steps[it].append(str(c.get('name') or ''))
    paired = False
    if has_iter:
        for names in steps.values():
            if 'city_feature_identifier' in names and 'city_reputation_identifier' in names:
                paired = True
                break
    cfi = counts.get('city_feature_identifier', 0)
    cri = counts.get('city_reputation_identifier', 0)
    if cfi == 0 and cri == 0:
        reasons.append('city_feature_identifier and city_reputation_identifier never invoked together')
    elif not has_iter:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'cannot determine if city_feature_identifier and city_reputation_identifier invoked in same step (no iteration info)', 'evidence_refs': []}
    elif not paired:
        reasons.append('city_feature_identifier and city_reputation_identifier not invoked together in a single step')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'total in range, per-tool caps respected, paired city tools in same step', 'evidence_refs': []}
