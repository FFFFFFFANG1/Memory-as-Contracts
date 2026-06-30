def evaluate(trace):
    import re
    final=(trace.get('final_response') or '')
    calls=trace.get('tool_calls') or []
    used=[]
    for c in calls:
        n=c.get('name')
        if n and n not in used:
            used.append(n)
    if not used:
        return {'observed_followed':None,'confidence':'unknown','reason':'No tool calls in trajectory to cite.','evidence_refs':[]}
    if not final.strip():
        return {'observed_followed':None,'confidence':'unknown','reason':'No final response to inspect.','evidence_refs':[]}
    mentioned=[n for n in used if n in final]
    missing=[n for n in used if n not in final]
    if not mentioned:
        return {'observed_followed':False,'confidence':'high','reason':'No tool names from trajectory appear in the response body.','evidence_refs':used}
    if missing:
        return {'observed_followed':False,'confidence':'medium','reason':f'Tool names missing from response: {missing}','evidence_refs':missing}
    return {'observed_followed':True,'confidence':'medium','reason':'All used tool names appear in the response body alongside content.','evidence_refs':mentioned}
