def evaluate(trace):
    import re
    tools = ['biographical_info_retriever','highest_mountain_finder','historical_event_locator','island_identifier','nearby_mountain_locator','public_transport_locator','species_locator']
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_call = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            found_call = True
            break
        c = step.get('content') or ''
        if isinstance(c, str):
            pre_text += '\n' + c
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No scratchpad content before first tool call','evidence_refs':[]}
    low = pre_text.lower()
    missing = [t for t in tools if t.lower() not in low]
    if missing:
        return {'observed_followed': False,'confidence':'high','reason':f'Tools not enumerated before first call: {missing}','evidence_refs':[]}
    # check for schema/input mentions
    schema_hints = ['input','schema','parameter','argument','arg:','param','expects','takes']
    hint_count = sum(1 for h in schema_hints if h in low)
    if hint_count < 1:
        return {'observed_followed': False,'confidence':'medium','reason':'No mention of input schema/parameters in scratchpad','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'All tools and input schemas enumerated before first substantive tool call','evidence_refs':[]}
