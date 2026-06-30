def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    last = tcs[-1]
    name = last.get('name') or last.get('tool') or ''
    if name != 'national_symbol_finder':
        return {'observed_followed': False, 'confidence':'high','reason':f'last tool was {name}','evidence_refs':[{'index':last.get('index')}]}
    result = last.get('result')
    if result is None:
        return {'observed_followed': None,'confidence':'unknown','reason':'no result captured','evidence_refs':[]}
    final = trace.get('final_response') or ''
    res_str = result if isinstance(result, str) else str(result)
    snippet = res_str.strip()
    if not snippet:
        return {'observed_followed': None,'confidence':'unknown','reason':'empty result','evidence_refs':[]}
    if snippet in final:
        return {'observed_followed': True,'confidence':'high','reason':'verbatim output present and last tool correct','evidence_refs':[{'index':last.get('index')}]}
    # try partial: check if a substantial portion is present
    import re
    tokens = [t for t in re.split(r'\s+', snippet) if t]
    if tokens:
        joined = ' '.join(tokens)
        if joined in final:
            return {'observed_followed': True,'confidence':'high','reason':'verbatim output present','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'tool output not reported verbatim in final response','evidence_refs':[{'index':last.get('index')}]}
