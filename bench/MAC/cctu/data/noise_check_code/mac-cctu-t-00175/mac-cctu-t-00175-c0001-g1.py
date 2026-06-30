def evaluate(trace):
    traj = trace.get('trajectory') or []
    turns = 0
    bad = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if not tcs:
            continue
        turns += 1
        if len(tcs) != 1:
            bad.append({'turn_index': i, 'tool_call_count': len(tcs)})
    if turns == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool-invoking turns found.', 'evidence_refs': []}
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Some turns invoked != 1 tool.', 'evidence_refs': bad}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Every tool-invoking turn used exactly one tool call.', 'evidence_refs': []}
