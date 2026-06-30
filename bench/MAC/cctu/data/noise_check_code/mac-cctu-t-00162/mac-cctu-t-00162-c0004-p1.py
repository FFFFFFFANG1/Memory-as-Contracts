def evaluate(trace):
    import re
    traj = trace.get('trajectory', []) or []
    pre_tool_text = []
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            if content:
                pre_tool_text.append(content)
            break
        if content:
            pre_tool_text.append(content)
    if not trace.get('tool_calls'):
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls in trace','evidence_refs':[]}
    text = '\n'.join(pre_tool_text)
    if not text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'no pre-tool content; checklist missing','evidence_refs':[]}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\(?\d+[\).\:\-]|\d+\s)', l)]
    if len(numbered) >= 2:
        return {'observed_followed': True, 'confidence':'medium','reason':f'found {len(numbered)} numbered items before first tool','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':'no numbered checklist of sub-questions before first tool','evidence_refs':[]}
