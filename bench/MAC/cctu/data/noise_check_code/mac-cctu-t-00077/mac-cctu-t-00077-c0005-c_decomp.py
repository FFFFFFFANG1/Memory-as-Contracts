def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_tool_text = []
    first_tool_step = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            first_tool_step = i
            # include content of this step only if it precedes tool calls textually; safer to include
            if content:
                pre_tool_text.append(content)
            break
        if content:
            pre_tool_text.append(content)
    if first_tool_step is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory', 'evidence_refs': []}
    text = '\n'.join(pre_tool_text)
    if not text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No pre-tool content; checklist missing', 'evidence_refs': []}
    # Find numbered list items like '1.' '2.' or '1)' on separate lines
    lines = text.splitlines()
    numbered = []
    for ln in lines:
        m = re.match(r'\s*(\d+)[\.\)]\s+\S', ln)
        if m:
            numbered.append(int(m.group(1)))
    # Need at least 2 sequential numbered items starting at 1
    ok = len(numbered) >= 2 and numbered[0] == 1 and all(numbered[i]==numbered[i-1]+1 for i in range(1,len(numbered)))
    if ok:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Found numbered checklist with {len(numbered)} items before first tool call', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'No complete numbered checklist before first tool call (found numbers: {numbered})', 'evidence_refs': []}
