def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    hel_indices = [i for i, c in enumerate(calls) if c.get('name') == 'historical_exploration_locator']
    linkage_tools = {'historical_exploration_locator', 'explorer_archipelago_matcher'}
    downstream_indices = [i for i, c in enumerate(calls) if c.get('name') not in linkage_tools]
    if len(hel_indices) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'historical_exploration_locator called {len(hel_indices)} time(s); need >=2', 'evidence_refs': [{'hel_calls': len(hel_indices)}]}
    # Check independence: at least 2 returns with non-empty distinct results
    results = []
    for i in hel_indices:
        r = calls[i].get('result')
        if r is not None and r != '':
            results.append(str(r))
    distinct = len(set(results))
    if distinct < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'only {distinct} distinct non-empty returns from historical_exploration_locator', 'evidence_refs': [{'distinct_returns': distinct}]}
    # Ensure the 2nd HEL call precedes any downstream lookup
    second_hel = hel_indices[1]
    early_downstream = [i for i in downstream_indices if i < second_hel]
    if early_downstream:
        names = [calls[i].get('name') for i in early_downstream]
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'downstream tools {names} called before 2 HEL confirmations', 'evidence_refs': [{'early_downstream_indices': early_downstream}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': '>=2 independent HEL returns precede downstream lookups', 'evidence_refs': [{'hel_indices': hel_indices, 'distinct_returns': distinct}]}
