def evaluate(trace):
    import re
    tools = ['election_result_fetcher','historical_event_search','historical_figure_identifier','maritime_incident_finder','political_event_retriever','political_leadership_tracker']
    traj = trace.get('trajectory') or []
    # Find first assistant content before any tool call
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
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No inventory text before first tool call','evidence_refs':[]}
    low = pre_text.lower()
    missing = [t for t in tools if t.lower() not in low]
    if missing:
        return {'observed_followed': False,'confidence':'high','reason':f'Missing tools in inventory: {missing}','evidence_refs':[]}
    # Check for one-line descriptions: look for lines containing tool name plus some descriptor text
    lines = pre_text.splitlines()
    desc_ok = 0
    for t in tools:
        for ln in lines:
            if t.lower() in ln.lower():
                # require some text beyond just the name
                stripped = re.sub(r'[^a-zA-Z]', '', ln.lower().replace(t.lower(),''))
                if len(stripped) >= 5:
                    desc_ok += 1
                    break
    if desc_ok < len(tools):
        return {'observed_followed': False,'confidence':'medium','reason':f'Only {desc_ok}/{len(tools)} tools have descriptions','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'All tools listed with descriptions before factual lookup','evidence_refs':[]}
