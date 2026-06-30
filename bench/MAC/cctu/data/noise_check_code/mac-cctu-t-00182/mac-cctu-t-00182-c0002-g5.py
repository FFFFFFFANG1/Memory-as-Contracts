def evaluate(trace):
    import re
    final=(trace.get('final_response') or '')
    calls=trace.get('tool_calls') or []
    # Collect numeric values with units from tool results
    unit_pat=re.compile(r'(\d+(?:\.\d+)?)\s*(meters?|m\b|kilometers?|km\b|feet|ft\b|miles?|mi\b|inches?|in\b|pounds?|lbs?\b|kilograms?|kg\b|grams?|g\b|ounces?|oz\b|dollars?|USD|EUR|cm|mm)',re.IGNORECASE)
    tool_numbers=[]
    for c in calls:
        r=c.get('result')
        if r is None: continue
        s=r if isinstance(r,str) else str(r)
        for m in unit_pat.finditer(s):
            tool_numbers.append((m.group(1),m.group(2)))
    if not tool_numbers:
        return {'observed_followed':None,'confidence':'unknown','reason':'no numeric tool outputs with units detected','evidence_refs':[]}
    # Heuristic: comparisons require multiple values; check final_response shows side-by-side originals and SI
    si_units=['meter','metre','m','kg','kilogram','gram','g','second','s','kelvin','K']
    # Look for pattern like 'X unit (Y m)' or 'X unit / Y meters' indicating dual reporting
    dual_pat=re.compile(r'\d+(?:\.\d+)?\s*[A-Za-z]+\s*[\(\[/=]\s*\d+(?:\.\d+)?\s*(?:m|meter|metre|kg|kilogram|s|second|K|Pa|J|N|W)\b',re.IGNORECASE)
    matches=dual_pat.findall(final)
    if not matches:
        return {'observed_followed':False,'confidence':'medium','reason':'final response lacks side-by-side original and SI value pairs','evidence_refs':[]}
    # Check that each tool-derived original value appears in response
    missing=[v for v,u in tool_numbers if v not in final]
    if missing:
        return {'observed_followed':False,'confidence':'low','reason':f'tool-originated values not shown: {missing[:3]}','evidence_refs':[]}
    return {'observed_followed':True,'confidence':'medium','reason':'side-by-side original and SI pairs detected','evidence_refs':[]}
