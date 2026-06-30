def evaluate(trace):
    import json, re
    final = trace.get('final_response') or ''
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    m = re.search(r'Tool Evidence', final, re.IGNORECASE)
    if not m:
        return {'observed_followed': False,'confidence':'high','reason':'missing Tool Evidence section','evidence_refs':[]}
    section = final[m.end():]
    missing = []
    for c in calls:
        res = c.get('result')
        if res is None:
            continue
        if isinstance(res,(dict,list)):
            try:
                raw = json.dumps(res)
            except Exception:
                raw = str(res)
        else:
            raw = str(res)
        snippet = raw.strip()[:60]
        if snippet and snippet not in section:
            missing.append(c.get('name',''))
    if missing:
        return {'observed_followed': False,'confidence':'medium','reason':f'missing verbatim responses for {missing}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'Tool Evidence section present with tool responses','evidence_refs':[]}
