def evaluate(trace):
    import re
    tools=['celestial_discovery_info','flight_price_checker','historical_event_data_info_retriever','historical_event_finder','population_data_retriever','social_media_metrics_tool','space_mission_info_retriever','tourism_statistics_tool']
    traj=trace.get('trajectory') or []
    # find first assistant step that issues a tool call and first step that lists tools
    first_call_idx=None
    inventory_idx=None
    for i,step in enumerate(traj):
        content=(step.get('content') or '') if isinstance(step,dict) else ''
        tcs=step.get('tool_calls') or [] if isinstance(step,dict) else []
        if inventory_idx is None and content:
            low=content.lower()
            found=sum(1 for t in tools if t.lower() in low)
            if found>=len(tools):
                inventory_idx=i
        if first_call_idx is None and tcs:
            first_call_idx=i
    if first_call_idx is None and inventory_idx is None:
        return {'observed_followed':None,'confidence':'unknown','reason':'No tool calls and no inventory found','evidence_refs':[]}
    if inventory_idx is None:
        return {'observed_followed':False,'confidence':'high','reason':'No enumeration of all tools found in trajectory','evidence_refs':[]}
    if first_call_idx is None:
        return {'observed_followed':True,'confidence':'medium','reason':'Inventory present and no data retrieval calls made','evidence_refs':[]}
    if inventory_idx < first_call_idx:
        # also check that some sign-off indicator or at least a user turn followed; lenient: inventory before first call
        return {'observed_followed':True,'confidence':'high','reason':f'Inventory at step {inventory_idx} precedes first tool call at {first_call_idx}','evidence_refs':[]}
    return {'observed_followed':False,'confidence':'high','reason':f'Tool call at step {first_call_idx} issued before inventory at step {inventory_idx}','evidence_refs':[]}
