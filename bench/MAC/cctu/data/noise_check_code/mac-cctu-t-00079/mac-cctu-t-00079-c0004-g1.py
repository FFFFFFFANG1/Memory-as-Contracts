def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').strip()
    if not tcs and not final:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no evidence','evidence_refs':[]}
    first_ok = None
    if tcs:
        first = tcs[0].get('name','')
        first_ok = (first == 'music_info_retriever')
    prefix_ok = None
    if final:
        prefix_ok = final.startswith('[HERITAGE]')
        if prefix_ok:
            rest = final[len('[HERITAGE]'):].strip()
            if not rest:
                prefix_ok = False
    checks = [v for v in (first_ok, prefix_ok) if v is not None]
    if not checks:
        return {'observed_followed': None,'confidence':'unknown','reason':'insufficient evidence','evidence_refs':[]}
    followed = all(checks)
    return {'observed_followed': followed,'confidence':'high' if (first_ok is not None and prefix_ok is not None) else 'medium','reason': f'first_tool_ok={first_ok}, prefix_ok={prefix_ok}','evidence_refs':[]}
