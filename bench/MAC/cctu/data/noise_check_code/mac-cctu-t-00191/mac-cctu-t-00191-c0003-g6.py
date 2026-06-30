def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    calls = trace.get('tool_calls',[]) or []
    nums = re.findall(r'\d+(?:\.\d+)?', final)
    if not nums:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no numeric values in response','evidence_refs':[]}
    def res_str(c):
        r = c.get('result','')
        try:
            return r if isinstance(r,str) else str(r)
        except Exception:
            return ''
    results = [(c.get('name',''), res_str(c)) for c in calls]
    if not results:
        return {'observed_followed': False, 'confidence':'high','reason':'numeric values present but no tool calls recorded','evidence_refs':[]}
    unverified = []
    for n in nums:
        matching_tools = set()
        for name, r in results:
            if re.search(r'(?<!\d)' + re.escape(n) + r'(?!\d)', r):
                matching_tools.add(name)
        if len(matching_tools) < 2:
            unverified.append((n, sorted(matching_tools)))
    if unverified:
        return {'observed_followed': False, 'confidence':'medium','reason':f'values not verified by 2 independent tool calls: {unverified}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'all numeric values appear in results of >=2 distinct tool calls','evidence_refs':[]}
