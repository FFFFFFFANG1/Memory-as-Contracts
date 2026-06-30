def evaluate(trace):
    traj = trace.get('trajectory') or []
    assistant_steps = [s for s in traj if (s.get('role') == 'assistant') or s.get('tool_calls') is not None]
    tool_steps = [s for s in assistant_steps if s.get('tool_calls')]
    if not tool_steps:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found', 'evidence_refs': []}
    # Check commentary between tool calls: assistant steps with tool_calls should have empty/no text content
    commentary_violations = []
    for i, s in enumerate(tool_steps[:-1]):
        content = s.get('content')
        if isinstance(content, str) and content.strip():
            commentary_violations.append(i)
    # Check batching: count rounds with tool calls; if many single-call rounds, likely not batched
    rounds = [len(s.get('tool_calls') or []) for s in tool_steps]
    total_calls = sum(rounds)
    num_rounds = len(rounds)
    batched = any(r > 1 for r in rounds)
    # If multiple sequential single-call rounds without batching, flag
    multiple_sequential = num_rounds > 1 and not batched and total_calls > 1
    if commentary_violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'commentary present between tool calls at steps {commentary_violations}', 'evidence_refs': commentary_violations}
    if multiple_sequential:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{num_rounds} sequential single-call rounds suggest lookups were not batched', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'no inter-call commentary; {num_rounds} round(s) with sizes {rounds}', 'evidence_refs': []}
