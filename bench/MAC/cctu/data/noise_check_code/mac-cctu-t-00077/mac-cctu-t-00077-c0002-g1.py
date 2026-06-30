def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    first = None
    for step in traj:
        content = (step.get('content') or '').strip()
        tcs = step.get('tool_calls') or []
        if content:
            first = step
            break
        if tcs:
            first = step
            break
    if not first:
        return {'observed_followed': False,'confidence':'low','reason':'no initial planning content','evidence_refs':[]}
    if (first.get('tool_calls') or []) and not (first.get('content') or '').strip():
        return {'observed_followed': False,'confidence':'high','reason':'tool called before any planning text','evidence_refs':[]}
    text = first.get('content') or ''
    lines = text.splitlines()
    numbered = [l for l in lines if re.match(r'^\s*(\d+)[\.\)]\s+', l)]
    if len(numbered) < 2:
        return {'observed_followed': False,'confidence':'high','reason':'no numbered roadmap found','evidence_refs':[]}
    low = text.lower()
    mentions_tool = any(t.lower() in low for t in ['tool','invocation','call','retriev','finder','analyzer','locator','identifier'])
    mentions_expect = any(k in low for k in ['expect','observation','anticipat','should return','will return','result'])
    if not mentions_tool:
        return {'observed_followed': False,'confidence':'medium','reason':'numbered list lacks tool invocation references','evidence_refs':[]}
    if not mentions_expect:
        return {'observed_followed': False,'confidence':'medium','reason':'numbered list lacks expected observations','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'initial numbered roadmap with tools and expected observations present before tool calls','evidence_refs':[]}
