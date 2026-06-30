def evaluate(trace):
    import re
    tools=['advanced_arithmetic_calculator','biographical_affiliation_finder','biologist_specialization_finder','ecosystem_researcher_finder','enhanced_infrastructure_locator','forest_name_search','habitat_species_associator','historical_landmark_finder','landmark_info_retriever','nearby_forest_locator','park_area_calculator','tree_age_inquiry']
    resp=(trace.get('final_response') or '')
    calls=trace.get('tool_calls') or []
    if calls:
        return {'observed_followed':False,'confidence':'high','reason':f'{len(calls)} tool call(s) made during this step','evidence_refs':[]}
    low=resp.lower()
    missing=[t for t in tools if t.lower() not in low]
    if missing:
        return {'observed_followed':False,'confidence':'high','reason':f'Missing tools in enumeration: {missing}','evidence_refs':[]}
    # Check each tool appears to have some accompanying descriptive text (one-line summary)
    lines=[l for l in re.split(r'[\n\r]+',resp) if l.strip()]
    found_with_desc=0
    for t in tools:
        for l in lines:
            if t.lower() in l.lower() and len(l.strip())>len(t)+3:
                found_with_desc+=1
                break
    if found_with_desc<len(tools):
        return {'observed_followed':None,'confidence':'low','reason':f'Only {found_with_desc}/{len(tools)} tools have apparent one-line summaries','evidence_refs':[]}
    return {'observed_followed':True,'confidence':'high','reason':'All tools enumerated with summaries and no tool calls issued','evidence_refs':[]}
