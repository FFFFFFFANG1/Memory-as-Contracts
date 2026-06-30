def evaluate(trace):
    traj = trace.get('trajectory') or []
    offenders = []
    turns_with_calls = 0
    for i, step in enumerate(traj):
        calls = step.get('tool_calls') or []
        if not calls:
            continue
        turns_with_calls += 1
        if len(calls) > 1:
            offenders.append({'turn': i, 'count': len(calls)})
    if not trace.get('tool_calls') and not turns_with_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    if offenders:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found turns with multiple/parallel tool calls: {offenders}', 'evidence_refs': offenders}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {turns_with_calls} tool-using turns issued exactly one tool call with no parallelism.', 'evidence_refs': []}
