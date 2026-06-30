def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    used = any((c.get('name')=='historical_population_retriever') for c in calls)
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no final response', 'evidence_refs':[]}
    lines = [ln for ln in final.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence':'high', 'reason':'empty content', 'evidence_refs':[]}
    prefixed = [ln for ln in lines if ln.lstrip().startswith('>>>')]
    csv_like = all((',' in ln.split('>>>',1)[1]) for ln in prefixed) if prefixed else False
    marker_ok = len(prefixed) == len(lines) and len(prefixed) >= 1
    if not used:
        return {'observed_followed': False, 'confidence':'high', 'reason':'historical_population_retriever not invoked', 'evidence_refs':[c.get('name','') for c in calls]}
    if not marker_ok:
        return {'observed_followed': False, 'confidence':'high', 'reason':'final response lines not all prefixed with >>>', 'evidence_refs':[lines[0][:80] if lines else '']}
    if not csv_like:
        return {'observed_followed': False, 'confidence':'medium', 'reason':'prefixed lines do not look like CSV rows', 'evidence_refs':[prefixed[0][:80]]}
    return {'observed_followed': True, 'confidence':'high', 'reason':'tool used and CSV rows prefixed with >>>', 'evidence_refs':[prefixed[0][:80]]}
