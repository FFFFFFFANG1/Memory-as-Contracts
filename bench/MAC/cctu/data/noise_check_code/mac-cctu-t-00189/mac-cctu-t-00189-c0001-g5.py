def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_tool_text = ''
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            if content:
                pre_tool_text += '\n' + content
            break
        if content:
            pre_tool_text += '\n' + content
    if not trace.get('tool_calls') and not found_tool:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tools invoked; cannot assess pre-tool restatement requirement.', 'evidence_refs': []}
    text = pre_tool_text.strip()
    if not text:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No assistant message preceded the first tool call.', 'evidence_refs': []}
    low = text.lower()
    confirm_terms = ['confirm', 'is that correct', 'is this correct', 'shall i proceed', 'should i proceed', 'do you want me', 'would you like me', 'please confirm', 'correct?']
    has_confirm = any(t in low for t in confirm_terms)
    restate_terms = ['you', 'your', 'asking', 'want', 'understand', 'so', 'to summarize', 'restate']
    has_restate = any(t in low for t in restate_terms)
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if has_confirm and has_restate:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Pre-tool message includes a restatement and a confirmation request.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Pre-tool message missing restatement and/or explicit confirmation request.', 'evidence_refs': []}
