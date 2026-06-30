def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    calls = trace.get('tool_calls',[]) or []
    event_tools = {'global_event_reach_analyzer','historical_event_finder','historical_event_info_retriever','historical_event_tool','merged_historical_event_tool'}
    relevant = [c for c in calls if c.get('name') in event_tools]
    if not relevant:
        return {'observed_followed': None,'confidence':'unknown','reason':'No event-retrieval tool calls found','evidence_refs':[]}
    # Extract 4-digit years from final response as proxy for recorded event dates
    years = re.findall(r'\b(1[0-9]{3}|20[0-2][0-9])\b', final)
    if not years:
        return {'observed_followed': None,'confidence':'unknown','reason':'No dates detected in final response','evidence_refs':[]}
    # For each unique year, count how many distinct tool calls contain it in their result
    def result_text(c):
        r = c.get('result','')
        try:
            return r if isinstance(r,str) else str(r)
        except Exception:
            return ''
    texts = [(c.get('name',''), result_text(c)) for c in relevant]
    unverified = []
    for y in set(years):
        sources = set()
        for i,(name,txt) in enumerate(texts):
            if y in txt:
                sources.add((name,i))
        # Require at least 2 independent tool calls (preferably distinct tool names)
        distinct_names = {s[0] for s in sources}
        if len(sources) < 2 or len(distinct_names) < 2:
            unverified.append((y,len(sources),len(distinct_names)))
    if unverified:
        return {'observed_followed': False,'confidence':'medium','reason': f'Dates not cross-verified by 2 independent calls: {unverified}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'All detected dates appear in >=2 independent tool call results','evidence_refs':[]}
