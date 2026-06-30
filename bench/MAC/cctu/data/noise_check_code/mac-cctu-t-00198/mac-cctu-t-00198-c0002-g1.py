def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    first = traj[0]
    content = (first.get('content') or '').strip()
    tcs = first.get('tool_calls') or []
    if tcs:
        return {'observed_followed': False,'confidence':'high','reason':'initial step invoked tools','evidence_refs':[{'step':0,'tool_calls':len(tcs)}]}
    if not content:
        return {'observed_followed': None,'confidence':'low','reason':'no initial content','evidence_refs':[]}
    # Check plain text (no markdown headings, code fences, bold)
    if re.search(r'```', content) or re.search(r'\*\*[^*]+\*\*', content) or re.search(r'^#', content, re.M):
        return {'observed_followed': False,'confidence':'medium','reason':'initial content not plain text','evidence_refs':[{'step':0}]}
    # Check bullet list: at least 2 lines starting with -, *, or numbered
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    bullets = [l for l in lines if re.match(r'^([-*•]|\d+[.)])\s+', l)]
    if len(bullets) < 2:
        return {'observed_followed': False,'confidence':'medium','reason':'initial content is not a bullet list','evidence_refs':[{'bullets':len(bullets),'lines':len(lines)}]}
    return {'observed_followed': True,'confidence':'high','reason':'initial step is plain bullet list with no tools','evidence_refs':[{'bullets':len(bullets)}]}
