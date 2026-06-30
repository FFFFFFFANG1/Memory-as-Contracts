def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tools = ['disaster_impact_analyzer','election_result_analyzer','election_results_analyzer','freedom_status_tracker','historical_event_data_retriever','incident_locator','legal_case_info_retriever','political_office_tracker']
    pre_text = ''
    first_call_idx = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            first_call_idx = i
            break
        pre_text += ' ' + (step.get('content') or '')
    if first_call_idx is None:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls found','evidence_refs':[]}
    low = pre_text.lower()
    mentioned = [t for t in tools if t.lower() in low]
    # require mention of most tools and some schema-related vocabulary
    schema_kw = any(k in low for k in ['schema','input','parameter','argument','field','signature'])
    if len(mentioned) >= max(1, len(tools)-1) and schema_kw:
        return {'observed_followed': True, 'confidence':'medium','reason':f'pre-call content mentions {len(mentioned)} tools with schema vocabulary','evidence_refs':[]}
    if not schema_kw or len(mentioned) < len(tools)//2:
        return {'observed_followed': False, 'confidence':'medium','reason':f'pre-call content lacks schema catalog (tools mentioned={len(mentioned)}, schema_kw={schema_kw})','evidence_refs':[]}
    return {'observed_followed': None, 'confidence':'low','reason':'partial schema cataloging','evidence_refs':[]}
