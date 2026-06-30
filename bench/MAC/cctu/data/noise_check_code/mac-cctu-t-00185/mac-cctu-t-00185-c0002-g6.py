def evaluate(trace):
    traj = trace.get('trajectory') or []
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed.', 'evidence_refs': []}
    # Group tool calls by assistant turn (iteration)
    turns = {}
    for c in calls:
        it = c.get('iteration')
        if it is None:
            it = c.get('index')
        turns.setdefault(it, []).append(c.get('name'))
    turn_keys = sorted(turns.keys(), key=lambda x: (x is None, x))
    turns_with_calls = [k for k in turn_keys if turns[k]]
    if len(turns_with_calls) <= 1:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {len(calls)} tool call(s) issued in a single batched turn.', 'evidence_refs': [{'turns_with_calls': len(turns_with_calls), 'batch_size': len(calls)}]}
    # Multiple sequential turns containing tool calls => likely sequential while pending
    per_turn = [{'turn': k, 'tools': turns[k]} for k in turns_with_calls]
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Tool calls span {len(turns_with_calls)} separate assistant turns instead of one batched action.', 'evidence_refs': per_turn}
