def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            break
        pre_text += '\n' + content
    if not found_tool:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls in trajectory', 'evidence_refs': []}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\(?\d+[\.\)]|\d+\s)', l)]
    if len(numbered) >= 2:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'found {len(numbered)} numbered items before first tool call', 'evidence_refs': numbered[:5]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no numbered outline detected before first tool call', 'evidence_refs': [pre_text[:200]]}
