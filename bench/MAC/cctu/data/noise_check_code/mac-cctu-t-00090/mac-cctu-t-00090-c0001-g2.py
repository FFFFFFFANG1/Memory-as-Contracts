def evaluate(trace):
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    final_response = str(trace.get('final_response') or '')
    rounds = 0
    for step in trajectory:
        if isinstance(step, dict):
            content = step.get('content')
            if content and str(content).strip():
                rounds += 1
            tc = step.get('tool_calls') or []
            rounds += len(tc)
    if rounds == 0:
        rounds = len(tool_calls) + (1 if final_response.strip() else 0)
    if rounds == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory or tool call evidence available', 'evidence_refs': []}
    if rounds < 8:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'interaction rounds {rounds} below 8', 'evidence_refs': []}
    if rounds > 12:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'interaction rounds {rounds} above 12', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'interaction rounds {rounds} within [8,12]', 'evidence_refs': []}
