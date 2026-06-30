def evaluate(trace):
    import re
    tools = ['aviation_incident_finder','aviation_incident_retriever','geopolitical_event_finder','historical_event_finder','historical_event_info_retriever','historical_event_locator','political_leader_affiliation_finder']
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_pre = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if not tcs:
            pre_text += '\n' + (content or '')
        else:
            pre_text += '\n' + (content or '')
            found_pre = True
            break
    if not trace.get('tool_calls') and not found_pre:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls in trace','evidence_refs':[]}
    low = pre_text.lower()
    missing = [t for t in tools if t.lower() not in low]
    # check for input description cues
    input_cues = ['input','argument','parameter','expects','expected','takes']
    has_inputs = any(c in low for c in input_cues)
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason': f'pre-tool message missing tools: {missing}','evidence_refs':[]}
    if not has_inputs:
        return {'observed_followed': False, 'confidence':'medium','reason':'tools listed but inputs not described','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'all tools enumerated with input descriptions before first tool call','evidence_refs':[]}
