def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    first_tool_step = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            first_tool_step = i
            break
        pre_text += '\n' + content
    if first_tool_step is None:
        # No tool calls at all; constraint about ordering not violated, but roadmap may still be required before any call. Vacuously consider unknown.
        if re.search(r'(?m)^\s*1[\.\)]\s+\S', pre_text) and re.search(r'(?m)^\s*2[\.\)]\s+\S', pre_text):
            return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Numbered roadmap present; no tool calls issued.', 'evidence_refs': []}
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls and no clear roadmap detected.', 'evidence_refs': []}
    has_num1 = re.search(r'(?m)^\s*1[\.\)]\s+\S', pre_text)
    has_num2 = re.search(r'(?m)^\s*2[\.\)]\s+\S', pre_text)
    if has_num1 and has_num2:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Numbered roadmap recorded before first tool call.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'Tool call issued without a prior numbered roadmap in working notes.', 'evidence_refs': []}
