def evaluate(trace):
    calls = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    names = []
    for c in calls:
        n = c.get('name') or c.get('tool') or ''
        if n:
            names.append(n)
    distinct = set(names)
    if len(distinct) >= 2 and len(names) >= 2:
        return {'observed_followed': True, 'confidence':'low','reason':f'used {len(distinct)} distinct tools across {len(names)} calls; cross-verification plausible','evidence_refs':sorted(distinct)}
    if len(names) <= 1:
        return {'observed_followed': False, 'confidence':'high','reason':'fewer than two tool calls; cannot cross-verify','evidence_refs':names}
    return {'observed_followed': False, 'confidence':'medium','reason':'only one distinct tool source used; not independent cross-verification','evidence_refs':list(distinct)}
