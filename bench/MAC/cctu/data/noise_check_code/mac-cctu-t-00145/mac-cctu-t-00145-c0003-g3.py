def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l for l in resp.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False,'confidence':'high','reason':'no content','evidence_refs':[]}
    header = lines[0].lower().replace(' ','')
    expected_cols = {'category','brand','quantity'}
    header_cols = set(c.strip() for c in header.split(','))
    if not expected_cols.issubset(header_cols):
        return {'observed_followed': False,'confidence':'high','reason':f'header missing required columns: {lines[0]}','evidence_refs':[lines[0]]}
    # Check each remaining line is CSV-like (commas, no prose sentences)
    bad = []
    for l in lines[1:]:
        # must have at least 2 commas (3 fields)
        if l.count(',') < 2:
            bad.append(l)
    if bad:
        return {'observed_followed': False,'confidence':'high','reason':f'non-CSV lines found: {bad[:2]}','evidence_refs':bad[:3]}
    # Check for narrative markers around the CSV
    narrative_patterns = [r'here(\s|\')?s', r'below is', r'the following', r'note:', r'summary', r'as requested', r'please find']
    low = resp.lower()
    for p in narrative_patterns:
        if re.search(p, low):
            return {'observed_followed': False,'confidence':'high','reason':f'narrative text detected matching: {p}','evidence_refs':[p]}
    return {'observed_followed': True,'confidence':'high','reason':'CSV with required columns and no narrative','evidence_refs':[lines[0]]}
