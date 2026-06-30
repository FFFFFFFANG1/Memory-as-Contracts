def evaluate(trace):
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    # Check no parallel calls within a single assistant step
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if len(tcs) > 1:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'step {i} issued {len(tcs)} parallel tool calls', 'evidence_refs': [f'step:{i}']}
    # Check that between consecutive tool calls there is an assistant observation note
    # Walk trajectory: after each assistant step with a tool_call, before the next tool_call there should be assistant content verbalizing the result
    last_had_call = False
    missing = []
    for i, step in enumerate(traj):
        role = step.get('role', 'assistant')
        content = (step.get('content') or '').strip()
        tcs = step.get('tool_calls') or []
        if last_had_call and tcs:
            # New tool call issued without an intervening observation note
            # Check if this same step contains substantive content before the call
            if not content or len(content) < 10:
                missing.append(i)
        last_had_call = bool(tcs)
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'tool calls at steps {missing} lacked a verbalized observation note before issuing', 'evidence_refs': [f'step:{i}' for i in missing]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'sequential single tool calls with intervening notes', 'evidence_refs': []}
