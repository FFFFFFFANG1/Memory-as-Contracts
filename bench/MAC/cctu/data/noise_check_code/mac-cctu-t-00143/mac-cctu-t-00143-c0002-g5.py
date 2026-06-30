def evaluate(trace):
    import re
    final=(trace.get('final_response') or '')
    calls=trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed':None,'confidence':'unknown','reason':'no tool calls to verify','evidence_refs':[]}
    missing=[]
    for c in calls:
        idx=c.get('index'); name=c.get('name',''); res=c.get('result')
        res_str=res if isinstance(res,str) else (str(res) if res is not None else '')
        id_token=str(idx) if idx is not None else ''
        has_id = bool(id_token) and (id_token in final or f'#{id_token}' in final or f'call_{id_token}' in final or f'id={id_token}' in final)
        snippet=res_str.strip()[:40]
        has_payload = bool(snippet) and snippet in final
        if not (has_id and has_payload):
            missing.append({'index':idx,'name':name,'has_id':has_id,'has_payload':has_payload})
    if missing:
        return {'observed_followed':False,'confidence':'high','reason':f'missing id/payload for {len(missing)} call(s)','evidence_refs':missing[:5]}
    return {'observed_followed':True,'confidence':'medium','reason':'all tool call ids and payloads present in final response','evidence_refs':[]}
