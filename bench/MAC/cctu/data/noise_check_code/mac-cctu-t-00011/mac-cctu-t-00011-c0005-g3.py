def evaluate(trace):
    import re
    tools = ['election_result_fetcher','historical_event_search','historical_figure_identifier','maritime_incident_finder','political_event_retriever','political_leadership_tracker']
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_tool_call = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if not found_tool_call:
            pre_text += '\n' + content
            if tcs:
                found_tool_call = True
                break
    if not pre_text.strip() and not found_tool_call:
        pre_text = trace.get('final_response') or ''
    low = pre_text.lower()
    missing = [t for t in tools if t.lower() not in low]
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason': f'Missing tool enumeration before tool call: {missing}','evidence_refs':[]}
    # check parameters mentioned - look for 'parameter' or parens or colons indicating params
    has_param_marker = bool(re.search(r'param|argument|\(|:\s*\w', pre_text, re.I))
    if not has_param_marker:
        return {'observed_followed': None, 'confidence':'low','reason':'Tools listed but parameters not clearly declared','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'All tools and parameter info present before first tool call','evidence_refs':[]}
