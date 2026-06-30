def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    first_tool_step = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            first_tool_step = i
            break
        content = step.get('content') or ''
        if isinstance(content, str):
            pre_text += '\n' + content
    if first_tool_step is None:
        # No tool calls were made; constraint about 'before invoking any tool calls' is vacuously inapplicable
        if pre_text.strip():
            lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
            numbered = [l for l in lines if re.match(r'^(\(?\d+[\.\)]|\d+\s*[-:])', l)]
            if len(numbered) >= 2:
                return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Numbered roadmap present; no tools called.', 'evidence_refs': []}
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls and no clear roadmap to evaluate.', 'evidence_refs': []}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\(?\d+[\.\)]|\d+\s*[-:])', l)]
    if len(numbered) >= 2:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Found {len(numbered)} numbered items before first tool call.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'No numbered planning roadmap detected before first tool call.', 'evidence_refs': []}
