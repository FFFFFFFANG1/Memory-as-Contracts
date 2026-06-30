def evaluate(trace):
    import re
    final=trace.get('final_response','') or ''
    calls=trace.get('tool_calls',[]) or []
    if not calls:
        return {'observed_followed':None,'confidence':'unknown','reason':'no tool calls to cite','evidence_refs':[]}
    tool_names=[c.get('name','') for c in calls if c.get('name')]
    unique_tools=set(tool_names)
    # find parenthetical citations
    parens=re.findall(r'\(([^()]+)\)',final)
    cited=set()
    for p in parens:
        for t in unique_tools:
            if t and t in p:
                cited.add(t)
    missing=unique_tools-cited
    # check legal-status preference
    user_text=''
    for step in trace.get('trajectory',[]) or []:
        c=step.get('content','') or ''
        if isinstance(c,str):
            user_text+=' '+c
    full_ctx=(user_text+' '+final).lower()
    legal_q='legal status' in full_ctx or 'legal-status' in full_ctx
    used_finder=any(n=='historical_event_finder' for n in tool_names)
    used_fact=any(n=='historical_fact_retriever' for n in tool_names)
    pref_violation=legal_q and used_finder and not used_fact
    if missing:
        return {'observed_followed':False,'confidence':'medium','reason':f'tools not cited in parentheses: {sorted(missing)}','evidence_refs':[]}
    if pref_violation:
        return {'observed_followed':False,'confidence':'medium','reason':'legal-status question used historical_event_finder instead of historical_fact_retriever','evidence_refs':[]}
    return {'observed_followed':True,'confidence':'medium','reason':'all used tools cited; preference respected','evidence_refs':[]}
