def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = []
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            break
        if content:
            pre_text.append(content)
    if not found_tool:
        tcs_flat = trace.get('tool_calls') or []
        if not tcs_flat:
            return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed; cannot evaluate pre-tool decomposition requirement.', 'evidence_refs': []}
    text = '\n'.join(pre_text)
    if not text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No assistant content before first tool call; decomposition list missing.', 'evidence_refs': []}
    bullet_lines = [ln for ln in text.splitlines() if re.match(r'\s*([\-\*\+•]|\d+[\.\)])\s+\S', ln)]
    if len(bullet_lines) >= 2:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found {len(bullet_lines)} bulleted items before first tool call.', 'evidence_refs': bullet_lines[:5]}
 
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Pre-tool content lacks a bulleted decomposition list (need >=2 bullet items).', 'evidence_refs': [text[:200]]}
