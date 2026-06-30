def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    reasons = []
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls observed', 'evidence_refs': []}
    if len(tool_calls) != 2:
        reasons.append(f'expected exactly 2 tool invocations, got {len(tool_calls)}')
    names = [tc.get('name') for tc in tool_calls]
    if len(set(names)) != len(names):
        reasons.append(f'tool invocations not distinct: {names}')
    turns_with_tools = []
    for step in trajectory:
        tcs = step.get('tool_calls') or []
        if tcs:
            turn_names = [t.get('name') for t in tcs]
            turns_with_tools.append(turn_names)
    if turns_with_tools:
        if len(turns_with_tools) > 2:
            reasons.append(f'workflow used {len(turns_with_tools)} turns, expected 1 or 2')
        for i, tn in enumerate(turns_with_tools):
            if len(set(tn)) != 1:
                reasons.append(f'turn {i} uses multiple distinct tool types: {tn}')
    else:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'trajectory turn structure unavailable', 'evidence_refs': []}
    if not response.strip():
        reasons.append('empty final response')
    else:
        n = len(response)
        if n < 100 or n > 150:
            reasons.append(f'final response length {n} not in [100,150]')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all checks passed', 'evidence_refs': []}
