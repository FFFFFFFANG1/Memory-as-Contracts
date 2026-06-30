def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls to log','evidence_refs':[]}
    texts = []
    for step in traj:
        c = step.get('content')
        if isinstance(c, str):
            texts.append(c)
    blob = '\n'.join(texts)
    if not blob.strip():
        return {'observed_followed': False,'confidence':'medium','reason':'no logged YAML content in assistant steps','evidence_refs':[]}
    # Count YAML-like records with required fields
    tool_hits = len(re.findall(r'(?mi)^\s*-?\s*tool\s*:', blob))
    query_hits = len(re.findall(r'(?mi)^\s*query\s*:', blob))
    vs_hits = len(re.findall(r'(?mi)^\s*verification_status\s*:', blob))
    n = len(tool_calls)
    if tool_hits >= n and query_hits >= n and vs_hits >= n:
        return {'observed_followed': True,'confidence':'high','reason': f'found >={n} YAML records with tool/query/verification_status','evidence_refs':[]}
    if tool_hits == 0 and query_hits == 0 and vs_hits == 0:
        return {'observed_followed': False,'confidence':'high','reason':'no YAML log fields present','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason': f'incomplete YAML logging: tool={tool_hits} query={query_hits} verification_status={vs_hits} for {n} calls','evidence_refs':[]}
