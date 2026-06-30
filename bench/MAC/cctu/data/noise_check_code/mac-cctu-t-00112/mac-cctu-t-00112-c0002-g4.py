def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = resp.splitlines()
    bullet_re = re.compile(r'^\s*([\-\*\+•]|\d+[\.)])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    if not bullets:
        return {'observed_followed': False, 'confidence':'high','reason':'no bulleted list found','evidence_refs':[]}
    # Look for casualty/death numbers in bullets
    num_re = re.compile(r'\b\d[\d,]*\b')
    casualty_kw = re.compile(r'(kill|dead|death|casualt|fatalit|perish|died)', re.I)
    casualty_bullets = [b for b in bullets if casualty_kw.search(b) or num_re.search(b)]
    if not casualty_bullets:
        return {'observed_followed': None,'confidence':'low','reason':'bullets present but no casualty figures detected','evidence_refs':[]}
    # Check for arithmetic summation indicators outside bullets or in summary
    sum_indicators = re.compile(r'(total\s+(of\s+)?\d|sum\s+(of|is|=)|combined\s+(total|death|casualt)|altogether\s+\d|grand\s+total|in\s+total[,:]?\s*\d|aggregate\s+\d|\d+\s*\+\s*\d+\s*=|equals\s+\d+\s+(deaths|killed|casualt))', re.I)
    m = sum_indicators.search(resp)
    if m:
        return {'observed_followed': False,'confidence':'high','reason':f'arithmetic summation detected: {m.group(0)!r}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':f'{len(casualty_bullets)} bullet(s) with casualty figures, no summation detected','evidence_refs':[]}
