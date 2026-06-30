def evaluate(trace):
    import re
    tools = ['bank_failure_analyzer','corporate_event_retriever','diplomatic_relations_tracker','election_result_finder','event_location_finder','event_participation_finder','historical_event_finder','space_mission_info_retriever']
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
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No pre-tool-call content enumerating tools.','evidence_refs':[]}
    low = pre_text.lower()
    mentioned = [t for t in tools if t.lower() in low]
    # capability matrix heuristic: table markers or structured listing with descriptions
    has_table = ('|' in pre_text and pre_text.count('|') >= len(tools)) or bool(re.search(r'(capability|matrix|table)', low))
    has_descriptions = sum(1 for t in tools if t.lower() in low) >= len(tools)
    if len(mentioned) == len(tools) and (has_table or has_descriptions):
        return {'observed_followed': True, 'confidence':'high','reason':f'All {len(tools)} tools enumerated before any tool call with matrix/table structure.','evidence_refs':[]}
    if len(mentioned) < len(tools):
        return {'observed_followed': False, 'confidence':'high','reason':f'Only {len(mentioned)}/{len(tools)} tools enumerated before retrieval.','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':'Tools mentioned but no clear capability matrix structure.','evidence_refs':[]}
