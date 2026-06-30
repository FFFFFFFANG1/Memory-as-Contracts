def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    # find content before first tool call
    pre_text = ''
    first_idx = None
    for i, step in enumerate(traj):
        if step.get('tool_calls'):
            first_idx = i
            break
        c = step.get('content') or ''
        pre_text += '\n' + c
    # also include content in same step before tool calls
    if first_idx is not None:
        c = traj[first_idx].get('content') or ''
        pre_text += '\n' + c
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\(?\d+[\).\:\-]|\d+\s)', l)]
    has_numbered = len(numbered) >= 2
    # tool calls in this phase: assume 'this phase' = before any non-retrieval shift; approximate as first batch (same iteration as first tool call)
    first_iter = tool_calls[0].get('iteration')
    phase_calls = [t for t in tool_calls if t.get('iteration') == first_iter]
    within_limit = len(phase_calls) <= 2
    followed = has_numbered and within_limit
    reason = f'numbered_bullets_found={len(numbered)}, phase_tool_calls={len(phase_calls)}'
    return {'observed_followed': bool(followed), 'confidence':'medium','reason':reason,'evidence_refs':[]}
