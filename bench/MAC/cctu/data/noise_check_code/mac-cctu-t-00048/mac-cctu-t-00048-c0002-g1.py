def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l.strip() for l in resp.splitlines() if l.strip()]
    if len(lines) != 2:
        return {'observed_followed': False, 'confidence':'high','reason':f'expected 2 lines, got {len(lines)}','evidence_refs':[resp]}
    year_line, country_line = lines[0], lines[1]
    if not re.fullmatch(r'(?:19|20)\d{2}', year_line):
        return {'observed_followed': False, 'confidence':'high','reason':f'first line not a year: {year_line}','evidence_refs':[year_line]}
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]*", country_line):
        return {'observed_followed': False, 'confidence':'medium','reason':f'second line not a country: {country_line}','evidence_refs':[country_line]}
    return {'observed_followed': True, 'confidence':'high','reason':'two-line year then country','evidence_refs':[year_line, country_line]}
