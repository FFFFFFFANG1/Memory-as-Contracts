def evaluate(trace):
    import re
    final=trace.get('final_response','') or ''
    traj=trace.get('trajectory',[]) or []
    tool_calls=trace.get('tool_calls',[]) or []
    # Gather all text content from trajectory and final
    texts=[final]
    for s in traj:
        c=s.get('content','') if isinstance(s,dict) else ''
        if c: texts.append(c)
    blob='\n'.join(texts)
    fenced=re.findall(r'```[\s\S]*?```', blob)
    if not fenced:
        return {'observed_followed': False, 'confidence':'high','reason':'No fenced code block found recording dry-run schema responses.','evidence_refs':[]}
    # Identify tools actually used
    used=[]
    for tc in tool_calls:
        n=tc.get('name') if isinstance(tc,dict) else None
        if n and n not in used: used.append(n)
    if not used:
        return {'observed_followed': None,'confidence':'low','reason':'No tool calls present to verify dry-run authorization.','evidence_refs':[]}
    fenced_text='\n'.join(fenced).lower()
    missing=[t for t in used if t.lower() not in fenced_text]
    # Look for indication of dry-run / schema language
    has_schema_lang = any(k in blob.lower() for k in ['schema','dry-run','dry run','placeholder'])
    if missing:
        return {'observed_followed': False,'confidence':'medium','reason': f'Fenced code block does not mention dry-run schema for tools: {missing}','evidence_refs': fenced[:1]}
    if not has_schema_lang:
        return {'observed_followed': None,'confidence':'low','reason':'Fenced blocks present and mention tools but no clear schema/dry-run language.','evidence_refs': fenced[:1]}
    return {'observed_followed': True,'confidence':'medium','reason':'Fenced code block(s) recording dry-run schema responses for declared tools found.','evidence_refs': fenced[:1]}
