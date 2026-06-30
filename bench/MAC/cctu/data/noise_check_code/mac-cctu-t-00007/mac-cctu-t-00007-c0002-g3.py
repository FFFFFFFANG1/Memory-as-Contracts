def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    outline_found = False
    outline_idx = -1
    first_tool_idx = -1
    for i, step in enumerate(traj):
        content = (step.get('content') or '') if isinstance(step, dict) else ''
        tcs = step.get('tool_calls') or [] if isinstance(step, dict) else []
        if not outline_found and content:
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            numbered = [l for l in lines if re.match(r'^(\d+[\.)\:]|\(\d+\))\s+\S', l)]
            if len(numbered) >= 2:
                outline_found = True
                outline_idx = i
                if tcs:
                    return {'observed_followed': False,'confidence':'high','reason':'tool calls made in same step as outline draft','evidence_refs':[f'step{i}']}
        if tcs and first_tool_idx == -1:
            first_tool_idx = i
            break
    if first_tool_idx == -1:
        if outline_found:
            return {'observed_followed': True,'confidence':'medium','reason':'outline drafted; no tools called','evidence_refs':[f'step{outline_idx}']}
        return {'observed_followed': None,'confidence':'unknown','reason':'no tools and no clear outline','evidence_refs':[]}
    if not outline_found:
        return {'observed_followed': False,'confidence':'high','reason':'tool invoked without prior numbered outline','evidence_refs':[f'step{first_tool_idx}']}
    if outline_idx < first_tool_idx:
        return {'observed_followed': True,'confidence':'high','reason':'numbered outline precedes first tool call','evidence_refs':[f'outline_step{outline_idx}', f'first_tool_step{first_tool_idx}']}
    return {'observed_followed': False,'confidence':'high','reason':'outline not before tools','evidence_refs':[]}
