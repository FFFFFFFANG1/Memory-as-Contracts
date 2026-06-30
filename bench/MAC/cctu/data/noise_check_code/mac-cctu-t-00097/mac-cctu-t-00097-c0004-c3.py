def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    pre_text = ''
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            break
        pre_text += '\n' + str(content)
    if not found_tool:
        # no tools ever called; still check if roadmap exists in any pre content or final
        pre_text = pre_text or (trace.get('final_response') or '')
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\(?\d+[\.\)]|\d+\s*[-:])', l)]
    if len(numbered) >= 2:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Found {len(numbered)} numbered items before first tool call', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No numbered decomposition roadmap detected before first tool invocation', 'evidence_refs': []}
