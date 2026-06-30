def evaluate(trace):
    import re
    final=(trace.get('final_response') or '').strip()
    forbidden={'business_financial_data_retriever','chef_supplier_locator'}
    used=[c.get('name') for c in (trace.get('tool_calls') or [])]
    bad=[n for n in used if n in forbidden]
    if not final and not used:
        return {'observed_followed':None,'confidence':'unknown','reason':'no evidence','evidence_refs':[]}
    sentences=[s for s in re.split(r'(?<=[.!?])\s+', final) if s.strip()]
    too_long=len(sentences)>2
    if bad:
        return {'observed_followed':False,'confidence':'high','reason':f'used forbidden tools: {bad}','evidence_refs':bad}
    if too_long:
        return {'observed_followed':False,'confidence':'high','reason':f'response has {len(sentences)} sentences','evidence_refs':[]}
    return {'observed_followed':True,'confidence':'high','reason':'<=2 sentences and no forbidden tools','evidence_refs':[]}
