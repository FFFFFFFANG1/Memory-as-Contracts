def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    traj = trace.get('trajectory',[]) or []
    tool_calls = trace.get('tool_calls',[]) or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls to record.','evidence_refs':[]}
    texts = [final]
    for step in traj:
        c = step.get('content') if isinstance(step,dict) else None
        if c: texts.append(c)
    blob = '\n'.join(t for t in texts if isinstance(t,str))
    tool_names = {tc.get('name') for tc in tool_calls if tc.get('name')}
    tagged = {n for n in tool_names if re.search(r'\[\s*'+re.escape(n)+r'\s*\]', blob)}
    if not blob.strip():
        return {'observed_followed': None,'confidence':'unknown','reason':'No visible scratchpad/content to inspect.','evidence_refs':[]}
    if tagged == tool_names and tool_names:
        return {'observed_followed': True,'confidence':'medium','reason':f'All tools tagged in brackets: {sorted(tagged)}.','evidence_refs':[]}
    missing = tool_names - tagged
    if tagged and missing:
        return {'observed_followed': False,'confidence':'medium','reason':f'Missing bracket tags for: {sorted(missing)}.','evidence_refs':[]}
    if not tagged:
        return {'observed_followed': None,'confidence':'unknown','reason':'Scratchpad is internal; no bracket-tagged tool entries observed in visible trace.','evidence_refs':[]}
    return {'observed_followed': None,'confidence':'unknown','reason':'Indeterminate.','evidence_refs':[]}
