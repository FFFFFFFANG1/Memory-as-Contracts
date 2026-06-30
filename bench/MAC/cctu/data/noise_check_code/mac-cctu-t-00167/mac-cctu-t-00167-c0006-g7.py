def evaluate(trace):
    traj = trace.get('trajectory') or []
    offenders = []
    turns = 0
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if not tcs:
            continue
        turns += 1
        if len(tcs) > 1:
            offenders.append({'turn_index': i, 'tool_call_count': len(tcs)})
    if turns == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No assistant turns with tool calls found.', 'evidence_refs': []}
    if offenders:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(offenders)} turn(s) issued more than one tool call.', 'evidence_refs': offenders}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {turns} tool-invoking turn(s) used exactly one tool call.', 'evidence_refs': []}
