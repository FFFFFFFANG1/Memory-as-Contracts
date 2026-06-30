def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    if not tcs:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    first = tcs[0].get('name','')
    if first != 'constitutional_info_retriever':
        return {'observed_followed': False, 'confidence':'high','reason': f'first tool call is {first}','evidence_refs':[{'index':0,'name':first}]}
    pattern = re.compile(r'(article|section|amendment|clause|art\.|sec\.)\s*\w+', re.IGNORECASE)
    if not pattern.search(final):
        return {'observed_followed': False, 'confidence':'medium','reason':'no constitutional clause citation found in final','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'first call is constitutional_info_retriever and final cites a clause','evidence_refs':[]}
