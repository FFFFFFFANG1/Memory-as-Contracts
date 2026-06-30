def evaluate(trace):
    traj = trace.get('trajectory') or []
    turns_with_calls = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            turns_with_calls.append((i, len(tcs)))
    if not turns_with_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found in trajectory', 'evidence_refs': []}
    # Treat the first half of tool-using turns (at least first 2) as discovery phase
    n = len(turns_with_calls)
    discovery_count = max(2, n // 2)
    discovery = turns_with_calls[:discovery_count]
    violations = [(idx, c) for idx, c in discovery if c > 1]
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'parallel tool calls during discovery turns: {violations}', 'evidence_refs': [f'turn_{i}' for i,_ in violations]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'each of the first {discovery_count} tool-using turns made exactly one tool call', 'evidence_refs': [f'turn_{i}' for i,_ in discovery]}
