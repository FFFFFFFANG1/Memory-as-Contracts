def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    paragraphs = [p for p in re.split(r'\n\s*\n', resp.strip()) if p.strip()]
    if len(paragraphs) < 3:
        return {'observed_followed': False,'confidence':'high','reason':f'only {len(paragraphs)} paragraphs','evidence_refs':[]}
    # forbid tabular / JSON
    if '|' in resp and re.search(r'\|.*\|', resp):
        return {'observed_followed': False,'confidence':'medium','reason':'appears tabular (pipes)','evidence_refs':[]}
    if re.search(r'^\s*[-+]{3,}\s*$', resp, re.M):
        return {'observed_followed': False,'confidence':'medium','reason':'table separator detected','evidence_refs':[]}
    stripped = resp.strip()
    if (stripped.startswith('{') and stripped.endswith('}')) or (stripped.startswith('[') and stripped.endswith(']')):
        return {'observed_followed': False,'confidence':'high','reason':'JSON-like response','evidence_refs':[]}
    if re.search(r'```', resp):
        return {'observed_followed': False,'confidence':'medium','reason':'code block present','evidence_refs':[]}
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None,'confidence':'unknown','reason':'no tool calls to cite','evidence_refs':[]}
    missing = []
    for tc in tcs:
        idx = tc.get('index')
        if idx is None:
            continue
        patterns = [str(idx), f'[{idx}]', f'#{idx}', f'({idx})', f'call {idx}', f'tool {idx}']
        found = any(p in resp for p in patterns)
        if not found:
            missing.append(idx)
    if missing:
        return {'observed_followed': False,'confidence':'medium','reason':f'missing inline citation for indices {missing}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'prose with >=3 paragraphs, indices cited, no tables/JSON','evidence_refs':[]}
