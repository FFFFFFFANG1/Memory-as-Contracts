def evaluate(trace):
    import re
    tools = ['aviation_incident_finder','aviation_incident_retriever','geopolitical_event_finder','historical_event_finder','historical_event_info_retriever','historical_event_locator','political_leader_affiliation_finder']
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_tool_call = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            found_tool_call = True
            break
        c = step.get('content') or ''
        if isinstance(c, str):
            pre_text += '\n' + c
    if not trace.get('tool_calls') and not found_tool_call:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no retrieval tool invoked; constraint vacuous or N/A','evidence_refs':[]}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'no pre-tool message listing tools','evidence_refs':[]}
    low = pre_text.lower()
    missing = [t for t in tools if t.lower() not in low]
    suitability_terms = ['suitable','appropriate','suited','fit','use','select','choose','will use','best match','relevant']
    has_suit = any(term in low for term in suitability_terms)
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason':f'missing tool names before first call: {missing}','evidence_refs':[]}
    if not has_suit:
        return {'observed_followed': False, 'confidence':'medium','reason':'tools listed but no suitability confirmation','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'all tools listed and suitability confirmed before retrieval','evidence_refs':[]}
