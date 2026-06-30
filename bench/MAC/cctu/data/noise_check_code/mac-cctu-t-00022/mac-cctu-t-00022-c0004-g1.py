def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    saw_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            saw_tool = True
            break
        pre_text += '\n' + (content or '')
    if not saw_tool:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No pre-tool-call assistant content; outline missing.', 'evidence_refs': []}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    bullet_lines = [l for l in lines if re.match(r'^([-*+•]|\d+[.)])\s+', l)]
    has_bullets = len(bullet_lines) >= 2
    low = pre_text.lower()
    mentions_subq = any(k in low for k in ['sub-question','sub question','subquestion','sub-questions','subquestions'])
    mentions_tools = 'tool' in low
    ok = has_bullets and mentions_subq and mentions_tools
    return {
        'observed_followed': bool(ok),
        'confidence': 'high' if ok or not has_bullets else 'medium',
        'reason': f'pre_tool_bullets={len(bullet_lines)}, mentions_subquestions={mentions_subq}, mentions_tools={mentions_tools}',
        'evidence_refs': []
    }
