def evaluate(trace):
    import re, json
    traj = trace.get('trajectory') or []
    final = trace.get('final_response') or ''
    required = {'question','tool_used','raw_data'}
    found = False
    for step in traj:
        content = step.get('content') or ''
        if not content:
            continue
        for m in re.finditer(r'\{[\s\S]*?\}', content):
            snippet = m.group(0)
            try:
                obj = json.loads(snippet)
            except Exception:
                continue
            if isinstance(obj, dict) and required.issubset(obj.keys()):
                found = True
                break
            if isinstance(obj, list):
                for it in obj:
                    if isinstance(it, dict) and required.issubset(it.keys()):
                        found = True; break
        if found:
            break
    if not found:
        for m in re.finditer(r'\{[\s\S]*?\}', final):
            try:
                obj = json.loads(m.group(0))
            except Exception:
                continue
            if isinstance(obj, dict) and required.issubset(obj.keys()):
                found = True; break
    if found:
        return {'observed_followed': True, 'confidence':'high', 'reason':'Found JSON object with required keys question, tool_used, raw_data.', 'evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium', 'reason':'No JSON intermediate output with keys question/tool_used/raw_data detected.', 'evidence_refs':[]}
