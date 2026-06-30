def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    calls = trace.get('tool_calls') or []
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no response','evidence_refs':[]}
    lines = [l for l in resp.splitlines() if l.strip()]
    num_idx = None
    for i,l in enumerate(lines):
        if re.search(r'\d', l):
            num_idx = i
    if num_idx is None:
        return {'observed_followed': False,'confidence':'medium','reason':'no numerical answer line found','evidence_refs':[]}
    tail = '\n'.join(lines[num_idx+1:])
    if not tail.strip():
        return {'observed_followed': False,'confidence':'high','reason':'no citation block after numerical answer','evidence_refs':[]}
    if not calls:
        return {'observed_followed': None,'confidence':'low','reason':'no tool calls recorded to verify','evidence_refs':[]}
    missing = []
    for c in calls:
        name = c.get('name') or ''
        if name and name not in tail:
            missing.append(name)
    ts_pattern = re.compile(r'(\d{4}-\d{2}-\d{2}|\d{2}:\d{2}|timestamp)', re.I)
    has_ts = bool(ts_pattern.search(tail))
    if missing:
        return {'observed_followed': False,'confidence':'medium','reason':f'missing tools in citation: {missing}','evidence_refs':[]}
    if not has_ts:
        return {'observed_followed': False,'confidence':'medium','reason':'no timestamps in citation block','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'citation block enumerates tools with timestamps after numerical line','evidence_refs':[]}
