def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    first = traj[0]
    calls = first.get('tool_calls') or []
    names = set()
    for c in calls:
        n = c.get('name') or (c.get('function') or {}).get('name')
        if n:
            names.add(n)
    if len(names) < 5:
        return {'observed_followed': False, 'confidence':'high','reason': f'first turn had {len(names)} distinct tools: {sorted(names)}','evidence_refs':[]}
    final = trace.get('final_response') or ''
    if re.search(r'\d', final):
        m = re.findall(r'\d+', final)
        return {'observed_followed': False, 'confidence':'high','reason': f'final response contains numeric output: {m[:3]}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason': f'{len(names)} distinct tools in first turn and no digits in final','evidence_refs':[]}
