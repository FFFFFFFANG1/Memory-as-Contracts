def evaluate(trace):
    import re
    tools=['bank_failure_analyzer','corporate_event_retriever','diplomatic_relations_tracker','election_result_finder','event_location_finder','event_participation_finder','historical_event_finder','space_mission_info_retriever']
    traj=trace.get('trajectory') or []
    pre_text=''
    found_tool_call=False
    for step in traj:
        tcs=step.get('tool_calls') or []
        if tcs:
            found_tool_call=True
            break
        c=step.get('content')
        if isinstance(c,str):
            pre_text+='\n'+c
        elif isinstance(c,list):
            for p in c:
                if isinstance(p,dict) and isinstance(p.get('text'),str):
                    pre_text+='\n'+p['text']
    if not found_tool_call:
        return {'observed_followed':None,'confidence':'unknown','reason':'No external tool calls were issued; cannot verify pre-call enumeration.','evidence_refs':[]}
    if not pre_text.strip():
        return {'observed_followed':False,'confidence':'high','reason':'No working notes present before first tool call.','evidence_refs':[]}
    low=pre_text.lower()
    missing=[t for t in tools if t.lower() not in low]
    # Look for schema/signature indicators near tool names
    sig_indicators=['(',')','arg','param','schema','signature','->',':','input']
    has_sig=any(ind in low for ind in ['(',')','schema','signature','param','arg'])
    if missing:
        return {'observed_followed':False,'confidence':'high','reason':f'Pre-call notes missing tool names: {missing}','evidence_refs':[]}
    if not has_sig:
        return {'observed_followed':False,'confidence':'medium','reason':'Tool names listed but no schema/signature details found.','evidence_refs':[]}
    return {'observed_followed':True,'confidence':'medium','reason':'All tool names and signature-like info enumerated before first tool call.','evidence_refs':[]}
