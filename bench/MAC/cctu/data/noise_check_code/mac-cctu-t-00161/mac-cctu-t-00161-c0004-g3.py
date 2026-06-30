def evaluate(trace):
    import re
    final=trace.get('final_response','') or ''
    tool_calls=trace.get('tool_calls',[]) or []
    if not tool_calls:
        return {'observed_followed':None,'confidence':'unknown','reason':'No tool calls to attribute.','evidence_refs':[]}
    tool_names=set()
    for tc in tool_calls:
        n=tc.get('name')
        if n: tool_names.add(n)
    # Find citation-like patterns mentioning tool name and a field
    mentioned=[t for t in tool_names if t in final]
    # Heuristic: look for patterns like (tool_name: field) or [tool_name.field] or 'from tool_name, field='
    citation_patterns=[
        r'\(([a-z_]+)\s*[:\-\u2013]\s*([\w\.\s\-]+)\)',
        r'\[([a-z_]+)\s*[:\-\u2013\.]\s*([\w\.\s\-]+)\]',
        r'source[:\s]+([a-z_]+)[^a-z_]+field[:\s]+([\w\.\-]+)',
    ]
    hits=[]
    for pat in citation_patterns:
        for m in re.finditer(pat, final, re.IGNORECASE):
            if m.group(1).lower() in {t.lower() for t in tool_names}:
                hits.append(m.group(0))
    # Count sentence-like observations (rough): split on newline/period
    sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', final) if s.strip()]
    obs_sentences=[s for s in sentences if len(s)>20]
    if not obs_sentences:
        return {'observed_followed':None,'confidence':'unknown','reason':'No observations detected in final response.','evidence_refs':[]}
    # Each observation should have a citation referencing a tool name nearby
    cited=0
    for s in obs_sentences:
        if any(t in s for t in tool_names) and re.search(r'(field|:|\[|\(|\.)', s):
            cited+=1
    ratio=cited/len(obs_sentences) if obs_sentences else 0
    if ratio>=0.8 and hits:
        return {'observed_followed':True,'confidence':'medium','reason':f'{cited}/{len(obs_sentences)} observations carry tool+field citations.','evidence_refs':hits[:5]}
    if cited==0 and not hits:
        return {'observed_followed':False,'confidence':'high','reason':'No tool-name+field citations appended to observations.','evidence_refs':[]}
    return {'observed_followed':False,'confidence':'medium','reason':f'Only {cited}/{len(obs_sentences)} observations cite tool and field.','evidence_refs':hits[:5]}
