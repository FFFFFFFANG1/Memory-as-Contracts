def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    calls = trace.get('tool_calls',[]) or []
    names = [c.get('name','') for c in calls]
    has_fact = 'historical_fact_retriever' in names
    has_event = 'historical_event_data_info_retriever' in names
    # detect numerical figures in final response (years, counts, etc.)
    nums = re.findall(r'(?<![A-Za-z_])\d[\d,]*(?:\.\d+)?', final)
    if not nums:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No numerical figures detected in final response to cross-check.', 'evidence_refs':[]}
    if has_fact and has_event:
        return {'observed_followed': True, 'confidence':'medium', 'reason':'Both cross-check tools were called and figures are present.', 'evidence_refs':[{'tools_called': list(set(names))}]}
    return {'observed_followed': False, 'confidence':'high', 'reason':'Numerical figures reported but both required tools not called.', 'evidence_refs':[{'tools_called': list(set(names)), 'numbers_found': nums[:5]}]}
