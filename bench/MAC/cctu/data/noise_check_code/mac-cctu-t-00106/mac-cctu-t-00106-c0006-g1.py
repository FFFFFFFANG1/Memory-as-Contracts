def evaluate(trace):
    traj = trace.get('trajectory') or []
    # Find initial fact discovery phase: assistant steps that include tool_calls
    # Check that no assistant step in the early phase issues more than one tool call in parallel.
    tool_steps = []
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            tool_steps.append(len(tcs))
    if not tool_steps:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    # Initial fact discovery: take the first few tool-issuing steps (heuristic: first half or first 3)
    initial_n = max(1, min(len(tool_steps), max(3, len(tool_steps)//2)))
    initial = tool_steps[:initial_n]
    violations = [i for i, n in enumerate(initial) if n > 1]
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Parallel tool calls issued during initial fact discovery at step index(es) {violations} (counts={initial}).', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Initial {initial_n} tool-issuing step(s) each had exactly one tool call: {initial}.', 'evidence_refs': []}
