def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if not found_tool:
            if tcs:
                found_tool = True
                # include content of same step before tool calls
                if content:
                    pre_text += '\n' + content
                break
            else:
                pre_text += '\n' + content
    if not found_tool:
        # no tools invoked; constraint about ordering is vacuously not violated but also unclear
        # check if there were any tool calls overall
        if not (trace.get('tool_calls') or []):
            return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls in trajectory','evidence_refs':[]}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No pre-tool content; plan missing','evidence_refs':[]}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\(?\d+[\.\)]', l)]
    if len(numbered) < 2:
        return {'observed_followed': False, 'confidence':'high','reason':f'Found {len(numbered)} numbered items before first tool call','evidence_refs':[]}
    # Check that plan references tool calls/names
    text_low = pre_text.lower()
    tool_names = ['elevation_finder','geographical_feature_identifier','historical_event_locator','historical_geography_associator','landmark_age_retriever','philosopher_identifier','poet_identifier','political_leader_identifier']
    mentions = sum(1 for t in tool_names if t in text_low or t.replace('_',' ') in text_low)
    if mentions < 1:
        return {'observed_followed': False,'confidence':'medium','reason':'Numbered list does not reference tool calls by name','evidence_refs':[]}
    # Compare count of planned items to actual tool calls
    actual = len(trace.get('tool_calls') or [])
    if actual and len(numbered) < actual:
        return {'observed_followed': False,'confidence':'medium','reason':f'Plan has {len(numbered)} items but {actual} tool calls executed','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':f'Numbered plan with {len(numbered)} items emitted before tool calls','evidence_refs':[]}
