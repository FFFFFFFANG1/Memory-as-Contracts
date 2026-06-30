def evaluate(trace):
    import re
    tools=['advanced_arithmetic_calculator','biographical_affiliation_finder','biologist_specialization_finder','ecosystem_researcher_finder','enhanced_infrastructure_locator','forest_name_search','habitat_species_associator','historical_landmark_finder','landmark_info_retriever','nearby_forest_locator','park_area_calculator','tree_age_inquiry']
    traj=trace.get('trajectory') or []
    tcs=trace.get('tool_calls') or []
    # Collect assistant text before any tool call
    pre_text_parts=[]
    first_tool_iter=None
    for tc in tcs:
        it=tc.get('iteration')
        if it is not None:
            first_tool_iter=it if first_tool_iter is None else min(first_tool_iter,it)
    for step in traj:
        it=step.get('iteration')
        content=step.get('content') or ''
        if first_tool_iter is None or it is None or it<first_tool_iter:
            pre_text_parts.append(content)
        elif it==first_tool_iter:
            # include content of same step if tool call not yet executed in that message
            pre_text_parts.append(content)
    pre_text='\n'.join(pre_text_parts).lower()
    if not pre_text.strip():
        return {'observed_followed':False,'confidence':'high','reason':'No pre-tool documentation found.','evidence_refs':[]}
    # Check each tool name mention
    missing=[t for t in tools if t.lower() not in pre_text]
    # Check for schema language: input/output/schema/parameters/returns
    schema_terms=['input','output','schema','parameter','return','arg']
    has_schema_language=sum(1 for s in schema_terms if s in pre_text)>=2
    if missing:
        return {'observed_followed':False,'confidence':'high','reason':f'Tools not documented before binding: {missing}','evidence_refs':[]}
    if not has_schema_language:
        return {'observed_followed':False,'confidence':'medium','reason':'All tools mentioned but no input/output schema documentation language detected.','evidence_refs':[]}
    return {'observed_followed':True,'confidence':'medium','reason':'All tools surveyed with schema language prior to tool use.','evidence_refs':[]}
