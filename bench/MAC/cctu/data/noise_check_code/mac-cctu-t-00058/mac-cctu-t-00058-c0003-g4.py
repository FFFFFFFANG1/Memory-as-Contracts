def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    by_turn = {}
    for tc in tcs:
            key = tc.get('iteration')
            if key is None:
                key = tc.get('turn')
            if key is None:
                key = tc.get('step')
            by_turn.setdefault(key, []).append(tc)
    if len(by_turn) == 1 and None in by_turn:
        # fallback: treat assistant trajectory steps as turns
        traj = trace.get('trajectory') or []
        by_turn = {}
        for i, step in enumerate(traj):
            calls = step.get('tool_calls') or []
            if calls:
                by_turn[i] = calls
        if not by_turn:
            by_turn = {0: tcs}
    violations = []
    for k in sorted(by_turn.keys(), key=lambda x: (x is None, x)):
        calls = by_turn[k]
        if not calls:
            continue
        first = calls[0]
        name = first.get('name') or first.get('tool_name') or ''
        if name != 'cultural_information_retriever':
            violations.append({'turn': k, 'first_tool': name})
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Turns not starting with cultural_information_retriever: {violations}', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Every turn with tool calls began with cultural_information_retriever.', 'evidence_refs': [{'turns': sorted([k for k in by_turn.keys() if by_turn[k]], key=lambda x: (x is None, x))}]}
