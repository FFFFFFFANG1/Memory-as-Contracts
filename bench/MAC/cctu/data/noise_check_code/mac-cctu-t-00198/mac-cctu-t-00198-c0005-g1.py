def evaluate(trace):
    import re
    tools = ['advanced_arithmetic_calculator','biographical_affiliation_finder','biologist_specialization_finder','ecosystem_researcher_finder','enhanced_infrastructure_locator','forest_name_search','habitat_species_associator','historical_landmark_finder','landmark_info_retriever','nearby_forest_locator','park_area_calculator','tree_age_inquiry']
    traj = trace.get('trajectory') or []
    pre_text = ''
    first_tool_seen = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            first_tool_seen = True
            break
        c = step.get('content') or ''
        if isinstance(c, list):
            c = ' '.join(str(x) for x in c)
        pre_text += '\n' + str(c)
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No pre-tool message containing a checklist.','evidence_refs':[]}
    lines = pre_text.splitlines()
    numbered = [l for l in lines if re.match(r'\s*\d+[\.\)]\s+', l)]
    if len(numbered) < len(tools):
        return {'observed_followed': False,'confidence':'high','reason':f'Numbered checklist has {len(numbered)} items, need {len(tools)}.','evidence_refs':[]}
    low = pre_text.lower()
    missing = [t for t in tools if t.lower() not in low]
    if missing:
        return {'observed_followed': False,'confidence':'high','reason':f'Missing tools in checklist: {missing}','evidence_refs':[]}
    # Check each tool entry annotated with spatial or temporal
    bad = []
    for t in tools:
        # find line referencing this tool
        ref = None
        for l in numbered:
            if t.lower() in l.lower():
                ref = l
                break
        if ref is None:
            # maybe annotation is on adjacent line; search window
            idx = low.find(t.lower())
            ref = pre_text[max(0,idx-200):idx+200]
        rl = ref.lower()
        if 'spatial' not in rl and 'temporal' not in rl:
            bad.append(t)
    if bad:
        return {'observed_followed': False,'confidence':'medium','reason':f'Entries lacking spatial/temporal annotation: {bad}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'Numbered checklist of all tools with spatial/temporal annotations present before any tool call.','evidence_refs':[]}
