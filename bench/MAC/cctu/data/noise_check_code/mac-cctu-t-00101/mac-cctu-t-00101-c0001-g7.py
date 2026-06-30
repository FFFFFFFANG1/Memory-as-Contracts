def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    saw_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            saw_tool = True
            break
        c = step.get('content') or ''
        if isinstance(c, str):
            pre_text += '\n' + c
    if not saw_tool and not (trace.get('tool_calls') or []):
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls present to delimit planning phase','evidence_refs':[]}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No planning text before first tool call','evidence_refs':[]}
    numbered = re.findall(r'(?m)^\s*\d+[\.\)]\s+\S', pre_text)
    has_numbered = len(numbered) >= 2
    low = pre_text.lower()
    mentions_dep = any(k in low for k in ['depend','dependenc','prerequisite','requires','after ','before ','then '])
    if has_numbered and mentions_dep:
        return {'observed_followed': True,'confidence':'high','reason':f'Found {len(numbered)} numbered items and dependency language pre-tool-call','evidence_refs':[]}
    if has_numbered and not mentions_dep:
        return {'observed_followed': False,'confidence':'medium','reason':'Numbered list present but dependencies not mentioned','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'No numbered roadmap detected before first tool call','evidence_refs':[]}
