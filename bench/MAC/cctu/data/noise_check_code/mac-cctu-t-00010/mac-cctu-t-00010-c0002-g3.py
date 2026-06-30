def evaluate(trace):
    import re
    tools = ['bank_failure_analyzer','corporate_event_retriever','diplomatic_relations_tracker','election_result_finder','event_location_finder','event_participation_finder','historical_event_finder','space_mission_info_retriever']
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_pre = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            if content:
                pre_text += '\n' + content
            found_pre = True
            break
        else:
            pre_text += '\n' + content
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    if not found_pre and not (trace.get('tool_calls')):
        return {'observed_followed': None,'confidence':'unknown','reason':'no retrieval calls were issued','evidence_refs':[]}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    bullet_lines = [l for l in lines if re.match(r'^([\-\*\+•]|\d+[\.)])\s+', l)]
    if not bullet_lines:
        return {'observed_followed': False,'confidence':'high','reason':'no bulleted list before retrieval','evidence_refs':[pre_text[:200]]}
    bullet_blob = '\n'.join(bullet_lines).lower()
    missing = [t for t in tools if t.lower() not in bullet_blob]
    if missing:
        return {'observed_followed': False,'confidence':'high','reason':f'missing tools in bullet list: {missing}','evidence_refs':bullet_lines}
    return {'observed_followed': True,'confidence':'high','reason':'all tools enumerated as bullets before retrieval','evidence_refs':bullet_lines}
