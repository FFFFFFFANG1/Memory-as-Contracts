def evaluate(trace):
    traj = trace.get('trajectory') or []
    offenders = []
    turns_with_calls = 0
    for i, step in enumerate(traj):
        if not isinstance(step, dict):
            continue
        tcs = step.get('tool_calls') or []
        if len(tcs) >= 1:
            turns_with_calls += 1
            if len(tcs) != 1:
                offenders.append({'turn': i, 'count': len(tcs)})
    if turns_with_calls == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No assistant turns with tool calls found', 'evidence_refs': []}
    if offenders:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(offenders)} turn(s) issued !=1 tool calls', 'evidence_refs': offenders[:5]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {turns_with_calls} tool-calling turns issued exactly one tool call', 'evidence_refs': []}
