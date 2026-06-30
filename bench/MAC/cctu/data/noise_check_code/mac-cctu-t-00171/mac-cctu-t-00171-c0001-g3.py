def evaluate(trace):
    import re
    tools=['artwork_artist_identifier','bibliographic_search_tool','biographical_info_retriever','biographical_residence_finder','historical_geography_associator','museum_dedication_finder','population_data_retriever','sports_award_tracker','tallest_building_finder','venue_capacity_checker']
    traj=trace.get('trajectory') or []
    pre_text=''
    first_call_idx=None
    for i,step in enumerate(traj):
        tcs=step.get('tool_calls') or []
        if tcs:
            first_call_idx=i
            break
        pre_text+=' '+(step.get('content') or '')
    final=trace.get('final_response') or ''
    text=pre_text if first_call_idx is not None else (pre_text+' '+final)
    if not text.strip():
        return {'observed_followed':None,'confidence':'unknown','reason':'no pre-invocation content captured','evidence_refs':[]}
    low=text.lower()
    named=[t for t in tools if t in low]
    missing=[t for t in tools if t not in low]
    schema_hint=bool(re.search(r'(schema|input|parameter|argument|arg|field|property|type\s*:)', low))
    if len(named)==len(tools) and schema_hint:
        return {'observed_followed':True,'confidence':'high','reason':'all tools enumerated with schema-related documentation before any invocation','evidence_refs':[]}
    if not named:
        return {'observed_followed':False,'confidence':'high','reason':'no tools enumerated before invocation','evidence_refs':[]}
    if missing:
        return {'observed_followed':False,'confidence':'medium','reason':f'missing tools before invocation: {missing}','evidence_refs':[]}
    return {'observed_followed':False,'confidence':'medium','reason':'tools listed but no input schema documentation detected','evidence_refs':[]}
