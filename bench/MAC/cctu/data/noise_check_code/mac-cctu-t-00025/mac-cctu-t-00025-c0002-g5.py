def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    # Find list-like items in final response
    lines = final.splitlines()
    bullet_re = re.compile(r'^\s*(?:[-*+\u2022]|\d+[\.)\]:]|[A-Za-z][\.)\]])\s+\S')
    items = [l for l in lines if bullet_re.match(l)]
    has_list = len(items) >= 5
    # Check pre-retrieval listing in trajectory
    retrieval_tools = {'historical_event_retriever','space_mission_info_retriever','historical_event_finder','diplomatic_event_finder','astronomical_event_identifier','conflict_group_identifier','election_result_analyzer','event_location_finder'}
    pre_text = ''
    found_pre_list = False
    for step in traj:
        calls = step.get('tool_calls') or []
        content = step.get('content') or ''
        if calls:
            # check if pre_text has list
            plines = pre_text.splitlines()
            pitems = [l for l in plines if bullet_re.match(l)]
            if len(pitems) >= 5:
                found_pre_list = True
            break
        pre_text += '\n' + content
    else:
        plines = pre_text.splitlines()
        pitems = [l for l in plines if bullet_re.match(l)]
        if len(pitems) >= 5:
            found_pre_list = True
    if not tool_calls:
        # No retrieval invoked; constraint about 'before invoking' is vacuous, but list must still be in response
        if has_list:
            return {'observed_followed': True, 'confidence':'medium','reason':f'Response contains {len(items)} list items; no retrieval tools invoked.','evidence_refs':[]}
        return {'observed_followed': False,'confidence':'medium','reason':'No 5+ item list in final response.','evidence_refs':[]}
    followed = has_list and found_pre_list
    reason = f'final_list_items={len(items)}, pre_retrieval_list={found_pre_list}'
    return {'observed_followed': bool(followed), 'confidence':'medium','reason':reason,'evidence_refs':[]}
