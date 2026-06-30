def evaluate(trace):
    traj = trace.get('trajectory') or []
    turns_with_tools = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            turns_with_tools.append((i, tcs))
    if not turns_with_tools:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool-calling turns found', 'evidence_refs': []}
    violations = []
    for idx, tcs in turns_with_tools:
        first = tcs[0]
        name = first.get('name') or (first.get('function') or {}).get('name')
        if name != 'diplomatic_recognition_tracker':
            violations.append({'turn_index': idx, 'first_tool': name})
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Turns not starting with diplomatic_recognition_tracker: {violations}', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Every tool-calling turn begins with diplomatic_recognition_tracker', 'evidence_refs': [{'turn_index': i} for i,_ in turns_with_tools]}
