def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    hist = [c for c in calls if (c.get('name') or '')=='historical_biological_catalog_query']
    bio = [c for c in calls if (c.get('name') or '')=='biologist_catalog_search']
    final = (trace.get('final_response') or '')
    has_appendix = bool(re.search(r'(audit\s+appendix|appendix[:\-\s].*audit|audit\s+log)', final, re.I))
    if not hist and not bio:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No relevant tool calls found to assess re-verification.','evidence_refs':[]}
    reverified = len(hist) >= 2 and len(bio) >= 2
    if reverified and has_appendix:
        return {'observed_followed': True,'confidence':'medium','reason':f'Both tools called >=2 times (hist={len(hist)}, bio={len(bio)}) and audit appendix present.','evidence_refs':[]}
    if not reverified:
        return {'observed_followed': False,'confidence':'high','reason':f'Re-verification missing: hist={len(hist)}, bio={len(bio)} (need >=2 each).','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'Re-verification calls present but no dedicated audit appendix detected in final response.','evidence_refs':[]}
