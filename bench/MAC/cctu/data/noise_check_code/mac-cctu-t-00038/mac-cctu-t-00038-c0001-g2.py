def evaluate(trace):
    resp = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    traj = trace.get('trajectory') or []
    reasons = []
    if not resp.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    # Check [Answer] identifier present
    if '[Answer]' not in resp:
        reasons.append('missing [Answer] identifier')
    else:
        idx = resp.rfind('[Answer]')
        after = resp[idx + len('[Answer]'):].strip()
        if not after:
            reasons.append('[Answer] not followed by final answer content')
    # Tool call count <= 3
    n_calls = len(tool_calls)
    if n_calls > 3:
        reasons.append('tool calls exceed 3 (got %d)' % n_calls)
    # Interaction rounds within [2,5]
    rounds = None
    try:
        iters = [c.get('iteration') for c in tool_calls if isinstance(c, dict) and c.get('iteration') is not None]
        if iters:
            rounds = len(set(iters))
    except Exception:
        rounds = None
    if rounds is None:
        rounds = len(traj) if traj else None
    if rounds is None:
        reasons.append('interaction rounds not observable')
        conf = 'low'
    else:
        if rounds < 2 or rounds > 5:
            reasons.append('interaction rounds %d outside [2,5]' % rounds)
        conf = 'high'
    if reasons:
        return {'observed_followed': False, 'confidence': conf, 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': conf, 'reason': '[Answer] identifier present, tool calls <=3, rounds within [2,5]', 'evidence_refs': []}
