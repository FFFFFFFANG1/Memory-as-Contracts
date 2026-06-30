def evaluate(trace):
    import re
    tools=['advanced_arithmetic_calculator','biographical_affiliation_finder','biologist_specialization_finder','ecosystem_researcher_finder','enhanced_infrastructure_locator','forest_name_search','habitat_species_associator','historical_landmark_finder','landmark_info_retriever','nearby_forest_locator','park_area_calculator','tree_age_inquiry']
    traj=trace.get('trajectory') or []
    pre_text=''
    first_tc_step=None
    for i,step in enumerate(traj):
        tcs=step.get('tool_calls') or []
        if tcs:
            first_tc_step=i
            break
        pre_text+='\n'+(step.get('content') or '')
    if first_tc_step is None:
        # no tool calls; check final/trajectory text
        pre_text+='\n'+(trace.get('final_response') or '')
    low=pre_text.lower()
    missing=[t for t in tools if t.lower() not in low]
    # matrix indicator
    has_matrix=any(k in low for k in ['capability matrix','| tool','matrix','capability'])
    if not pre_text.strip():
        return {'observed_followed':False,'confidence':'high','reason':'No pre-call enumeration text found','evidence_refs':[]}
    if missing:
        return {'observed_followed':False,'confidence':'high','reason':f'Missing tools before first call: {missing}','evidence_refs':[]}
    if not has_matrix:
        return {'observed_followed':False,'confidence':'medium','reason':'All tools listed but no capability matrix indicator','evidence_refs':[]}
    return {'observed_followed':True,'confidence':'high','reason':'All tools enumerated with capability matrix before external calls','evidence_refs':[]}
