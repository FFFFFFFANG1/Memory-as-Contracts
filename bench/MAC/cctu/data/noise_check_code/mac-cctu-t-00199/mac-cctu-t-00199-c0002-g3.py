def evaluate(trace):
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    turns = len(traj)
    # detect parallel: multiple tool_calls in a single assistant step
    parallel_found = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        if len(tcs) > 1:
            parallel_found = True
            break
    if not parallel_found:
        # fallback: group flattened tool_calls by iteration/index
        by_iter = {}
        for tc in tool_calls:
            key = tc.get('iteration')
            if key is None:
                continue
            by_iter.setdefault(key, 0)
            by_iter[key] += 1
        if any(v > 1 for v in by_iter.values()):
            parallel_found = True
    over_turns = turns > 5
    if turns == 0 and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory data', 'evidence_refs': []}
    if parallel_found or over_turns:
        reason = []
        if over_turns: reason.append(f'turns={turns} exceeds 5')
        if parallel_found: reason.append('parallel tool dispatch detected')
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reason), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'turns={turns} <=5 and serial tool execution', 'evidence_refs': []}
