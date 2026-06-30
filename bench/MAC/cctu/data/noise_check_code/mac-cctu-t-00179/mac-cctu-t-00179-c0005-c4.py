def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    # Find scoping step: an assistant message containing a numbered outline of intended tool calls
    data_tools = {'academic_paper_finder','architectural_designer_finder','biodiversity_database','biographical_info_retriever','capital_city_lookup','city_area_calculator','innovation_country_identifier','organization_locator','research_location_identifier','satellite_info_retriever','sports_venue_info'}
    def is_outline(text):
        if not text: return False
        lines=[l.strip() for l in text.splitlines() if l.strip()]
        numbered=[l for l in lines if re.match(r'^(\(?\d+[\).\:]|\d+\s)', l)]
        return len(numbered) >= 2
    scoping_idx = None
    for i, step in enumerate(traj):
        content = step.get('content') or ''
        tcs = step.get('tool_calls') or []
        if is_outline(content):
            scoping_idx = i
            # constraint: during this scoping step, no data tool invocations
            if tcs:
                names=[ (tc.get('name') or tc.get('function',{}).get('name','')) for tc in tcs]
                bad=[n for n in names if n in data_tools]
                if bad:
                    return {'observed_followed': False,'confidence':'high','reason': f'Scoping outline step also invoked data tools: {bad}','evidence_refs':[{'step':i,'tools':bad}]}
            break
    if scoping_idx is None:
        return {'observed_followed': None,'confidence':'unknown','reason':'No scoping step with numbered outline detected','evidence_refs':[]}
    # Also check no data tool calls occurred prior to or within the scoping step
    prior_bad=[]
    for tc in tool_calls:
        it = tc.get('iteration', tc.get('index'))
        name = tc.get('name','')
        if it is None: continue
        if it <= scoping_idx and name in data_tools:
            prior_bad.append({'iteration':it,'name':name})
    if prior_bad:
        return {'observed_followed': False,'confidence':'high','reason':'Data tools invoked during/before scoping','evidence_refs':prior_bad}
    return {'observed_followed': True,'confidence':'medium','reason':'Scoping step contains numbered outline with no data tool invocations','evidence_refs':[{'scoping_step':scoping_idx}]}
