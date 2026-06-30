def evaluate(trace):
    calls = trace.get('tool_calls') or []
    counts = {}
    for c in calls:
        if (c.get('name') or '') != 'historical_train_data_retriever':
            continue
        turn = c.get('iteration')
        if turn is None:
            turn = c.get('turn')
        counts[turn] = counts.get(turn, 0) + 1
    if not counts:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No calls to historical_train_data_retriever found.', 'evidence_refs': []}
    violations = [(t, n) for t, n in counts.items() if n > 3]
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Turns exceeding 3 calls: {violations}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'Per-turn counts within limit: {counts}', 'evidence_refs': []}
