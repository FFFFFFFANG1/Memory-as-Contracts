def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_names = ['academic_affiliation_finder_v2','advanced_calculator','age_calculator','artwork_artist_locator','biographical_info_retriever','culinary_origin_finder','desert_museum_locator','event_locator','explorer_achievement_finder','landmark_locator','nearby_establishment_finder','population_data_retriever']
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
        return {'observed_followed': False, 'confidence':'high','reason':'No pre-tool outline text found','evidence_refs':[]}
    low = pre_text.lower()
    mentioned_tools = [t for t in tool_names if t.lower() in low]
    # check for sub-question indicators
    has_questions = bool(re.search(r'\?', pre_text)) or bool(re.search(r'(?im)^\s*(sub[- ]?question|step\s*\d|\d+[\.)]|-\s+)', pre_text))
    has_outline_kw = bool(re.search(r'(?i)outline|decompos|plan|sub-?question', pre_text))
    if mentioned_tools and (has_questions or has_outline_kw):
        return {'observed_followed': True,'confidence':'medium','reason':f'Pre-tool outline mentions tools {mentioned_tools} and sub-questions/outline structure','evidence_refs':[]}
    if not found_tool_call:
        return {'observed_followed': None,'confidence':'unknown','reason':'No tool calls occurred; cannot verify pre-tool outline requirement','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':f'Pre-tool text lacks explicit sub-questions and/or tool mentions (tools_found={mentioned_tools}, has_questions={has_questions}, has_outline_kw={has_outline_kw})','evidence_refs':[]}
