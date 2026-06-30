def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    calls = trace.get('tool_calls') or []
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    n_calls = len(calls)
    if n_calls > 1:
        return {'observed_followed': False, 'confidence':'high','reason':f'{n_calls} tool calls exceed limit of 1','evidence_refs':[{'tool_calls':n_calls}]}
    if len(resp) > 60:
        return {'observed_followed': False, 'confidence':'high','reason':f'response length {len(resp)} > 60 chars','evidence_refs':[{'length':len(resp)}]}
    # single sentence: count sentence terminators not at end
    body = resp.rstrip()
    inner = body[:-1] if body and body[-1] in '.!?' else body
    if re.search(r'[.!?]\s+\S', inner):
        return {'observed_followed': False, 'confidence':'high','reason':'multiple sentences detected','evidence_refs':[{'text':resp}]}
    return {'observed_followed': True, 'confidence':'high','reason':'single sentence <=60 chars and <=1 tool call','evidence_refs':[{'length':len(resp),'tool_calls':n_calls}]}
