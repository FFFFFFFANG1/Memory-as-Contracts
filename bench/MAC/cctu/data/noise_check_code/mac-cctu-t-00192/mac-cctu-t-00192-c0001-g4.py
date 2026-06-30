def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    calls = trace.get('tool_calls',[]) or []
    ppc = [c for c in calls if (c.get('name') or '')=='product_price_comparator']
    # find numeric answers in final response (skip percentages themselves)
    # collect all numbers and their context
    nums = list(re.finditer(r'(?<![\w%])-?\d+(?:\.\d+)?(?!\s*%)', final))
    if not nums:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No numeric answers detected in final response','evidence_refs':[]}
    # check for confidence percentage presence near each number (within 80 chars)
    missing = []
    pct_pattern = re.compile(r'\d+(?:\.\d+)?\s*%')
    conf_pattern = re.compile(r'confidence', re.I)
    for m in nums:
        s = max(0, m.start()-80); e = min(len(final), m.end()+80)
        window = final[s:e]
        if not (pct_pattern.search(window) and conf_pattern.search(window)):
            missing.append(m.group())
    has_two_ppc = len(ppc) >= 2
    if missing:
        return {'observed_followed': False, 'confidence':'medium','reason':f'Numeric values without nearby confidence%: {missing[:3]}','evidence_refs':[]}
    if not has_two_ppc:
        return {'observed_followed': False, 'confidence':'high','reason':f'Only {len(ppc)} product_price_comparator calls; need 2 independent','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'Numeric answers carry confidence% and 2+ product_price_comparator calls present','evidence_refs':[]}
