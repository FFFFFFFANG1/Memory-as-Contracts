def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    treaty_calls = [c for c in calls if c.get('name')=='international_agreement_finder']
    if not treaty_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'international_agreement_finder not used; constraint conditional not triggered or no treaty data','evidence_refs':[]}
    # Look for any date-like token in tool results
    date_pat = re.compile(r'\b(1[89]\d{2}|20\d{2})\b')
    treaty_dates = []
    for c in treaty_calls:
        res = c.get('result')
        s = res if isinstance(res,str) else str(res)
        treaty_dates += date_pat.findall(s or '')
    if not treaty_dates:
        return {'observed_followed': None,'confidence':'unknown','reason':'no treaty dates returned by tool','evidence_refs':[]}
    text = final.lower()
    ipcc_recent = ('ar6' in text) or ('sixth assessment' in text) or ('6th assessment' in text)
    ipcc_any = 'ipcc' in text
    cited_date = any(d in final for d in treaty_dates)
    if ipcc_recent and cited_date:
        return {'observed_followed': True,'confidence':'high','reason':'AR6/sixth assessment cited alongside treaty date','evidence_refs':[]}
    if ipcc_any and cited_date and not ipcc_recent:
        return {'observed_followed': False,'confidence':'medium','reason':'IPCC mentioned but not the most recent (AR6) assessment','evidence_refs':[]}
    if not ipcc_any and cited_date:
        return {'observed_followed': False,'confidence':'high','reason':'treaty date present but no IPCC assessment cited','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'missing IPCC AR6 citation or treaty date in final response','evidence_refs':[]}
