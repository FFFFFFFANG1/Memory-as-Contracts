def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Detect forecast-like content: presence of percent signs
    pct_matches = re.findall(r'-?\d+(?:\.\d+)?\s*%', text)
    if not pct_matches:
        return {'observed_followed': None,'confidence':'unknown','reason':'no percentage forecasts found','evidence_refs':[]}
    # Find percentage ranges like X.X% to Y.Y% or X.X%-Y.Y%
    range_pattern = re.compile(r'(-?\d+(?:\.\d+)?)\s*%\s*(?:to|-|–|—|~)\s*(-?\d+(?:\.\d+)?)\s*%', re.IGNORECASE)
    ranges = range_pattern.findall(text)
    if not ranges:
        return {'observed_followed': False,'confidence':'high','reason':'percentages present but not formatted as ranges','evidence_refs':pct_matches[:5]}
    # Check each number in range has exactly one decimal place
    bad = []
    for a,b in ranges:
        for n in (a,b):
            if '.' not in n or len(n.split('.')[-1]) != 1:
                bad.append(n)
    if bad:
        return {'observed_followed': False,'confidence':'high','reason':f'numbers not rounded to single decimal: {bad}','evidence_refs':bad[:5]}
    # Check confidence interval mention
    ci_pattern = re.compile(r'confidence\s*interval|\bCI\b|\b\d{2,3}\s*%\s*(confidence|CI)', re.IGNORECASE)
    if not ci_pattern.search(text):
        return {'observed_followed': False,'confidence':'high','reason':'no confidence interval mentioned','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'percentage ranges with one decimal and CI present','evidence_refs':[f'{a}% to {b}%' for a,b in ranges[:3]]}
