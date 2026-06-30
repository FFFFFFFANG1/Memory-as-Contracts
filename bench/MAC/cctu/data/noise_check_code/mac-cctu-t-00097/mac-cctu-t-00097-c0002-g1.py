def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    # Find first assistant step
    first = None
    for step in traj:
        role = step.get('role','assistant')
        if role != 'assistant':
            continue
        first = step
        break
    if first is None:
        return {'observed_followed': None,'confidence':'unknown','reason':'no assistant step','evidence_refs':[]}
    content = first.get('content') or ''
    tcs = first.get('tool_calls') or []
    if tcs:
        return {'observed_followed': False,'confidence':'high','reason':'tools called in first/decomposition step','evidence_refs':[]}
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\(?\d+[\.\)]\s+\S', l)]
    if len(numbered) >= 2:
        return {'observed_followed': True,'confidence':'medium','reason':f'found {len(numbered)} numbered items before tools','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'no numbered bullet list found in decomposition phase','evidence_refs':[]}
