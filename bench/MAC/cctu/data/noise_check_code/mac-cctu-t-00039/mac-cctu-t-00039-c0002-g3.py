def evaluate(trace):
    import re
    final=(trace.get('final_response') or '')
    calls=trace.get('tool_calls') or []
    tools_used=[]
    for c in calls:
        n=c.get('name')
        if n and n not in tools_used:
            tools_used.append(n)
    if not tools_used:
        return {'observed_followed':None,'confidence':'unknown','reason':'no tool calls to cite','evidence_refs':[]}
    if not final.strip():
        return {'observed_followed':None,'confidence':'unknown','reason':'empty final response','evidence_refs':[]}
    missing=[]
    found=[]
    for t in tools_used:
        pattern=r'[\[\(\{<"\'`]\s*'+re.escape(t)+r'\s*[\]\)\}>"\'`]'
        if re.search(pattern,final,re.IGNORECASE) or re.search(r'(?:source|cite|via|from|ref|citation)[:\s]+'+re.escape(t),final,re.IGNORECASE):
            found.append(t)
        else:
            missing.append(t)
    has_any_marker=bool(re.search(r'[\[\(].+?[\]\)]',final))
    if not missing:
        return {'observed_followed':True,'confidence':'medium','reason':'all used tools appear as inline citation markers','evidence_refs':found}
    if not has_any_marker and not found:
        return {'observed_followed':False,'confidence':'high','reason':'no inline citation markers in response','evidence_refs':[]}
    return {'observed_followed':False,'confidence':'medium','reason':'missing citation markers for tools: '+','.join(missing),'evidence_refs':missing}
