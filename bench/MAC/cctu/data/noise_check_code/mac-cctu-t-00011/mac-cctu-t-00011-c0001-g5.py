def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    tool_calls = trace.get('tool_calls',[]) or []
    # find date-like claims in final response
    date_patterns = [r'\b\d{4}\b', r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}\b', r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', r'\b\d{4}-\d{2}-\d{2}\b']
    has_date_claim = any(re.search(p, final) for p in date_patterns)
    if not has_date_claim:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No date claim detected in final response.','evidence_refs':[]}
    distinct_tools = set()
    for c in tool_calls:
        name = c.get('name') or c.get('tool') or ''
        if name:
            distinct_tools.add(name)
    if len(distinct_tools) < 2:
        return {'observed_followed': False, 'confidence':'medium','reason':f'Date claim present but only {len(distinct_tools)} distinct retrieval tool(s) used.','evidence_refs':[{'distinct_tools':list(distinct_tools)}]}
    return {'observed_followed': True, 'confidence':'low','reason':f'Date claim present and {len(distinct_tools)} distinct tools used; agreement not verifiable automatically.','evidence_refs':[{'distinct_tools':list(distinct_tools)}]}
