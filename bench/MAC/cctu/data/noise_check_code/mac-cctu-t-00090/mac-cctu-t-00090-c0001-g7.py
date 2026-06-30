def evaluate(trace):
    traj = trace.get('trajectory') or []
    # Collect steps with tool_calls and intervening assistant text
    # Need: after each tool call completes, before next tool call, assistant wrote reflection text.
    tool_steps = []  # list of (step_index, has_tool_calls)
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = (step.get('content') or '').strip()
        tool_steps.append({'i': i, 'tcs': tcs, 'content': content})
    # Identify indices where tool calls occurred
    tc_indices = [s['i'] for s in tool_steps if s['tcs']]
    if len(tc_indices) <= 1:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Not enough tool invocations to assess reflections between them.', 'evidence_refs': []}
    violations = []
    reflections = 0
    for k in range(len(tc_indices) - 1):
        a = tc_indices[k]
        b = tc_indices[k+1]
        # Look at steps strictly between a and b for assistant reflection text
        between_text = []
        for j in range(a+1, b):
            c = (traj[j].get('content') or '').strip()
            if c:
                between_text.append(c)
        # Also allow reflection in same step as tool call if content present before next step
        same_step_text = (traj[a].get('content') or '').strip()
        combined = ' \n '.join(between_text) or same_step_text
        if not combined or len(combined) < 20:
            violations.append({'after_step': a, 'before_step': b})
        else:
            reflections += 1
    if violations:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Missing reflection between tool calls in {len(violations)} place(s).', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found reflection text between each of {len(tc_indices)-1} sub-task transitions.', 'evidence_refs': []}
