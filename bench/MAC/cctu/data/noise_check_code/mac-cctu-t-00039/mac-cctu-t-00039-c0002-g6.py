def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l for l in text.splitlines() if l.strip()]
    iso_re = re.compile(r'^\s*(?:[-*\d\.\)\(]+\s*)?(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)\b')
    entries = []
    for l in lines:
        m = iso_re.match(l)
        if m:
            entries.append((m.group(1), l))
    if len(entries) < 2:
        return {'observed_followed': None,'confidence':'low','reason':f'found {len(entries)} ISO-prefixed entries; insufficient to judge','evidence_refs':[]}
    # Check all non-trivial content lines are prefixed
    content_lines = [l for l in lines if re.search(r'[A-Za-z]', l) and not re.match(r'^\s*#', l)]
    unprefixed = [l for l in content_lines if not iso_re.match(l)]
    # Allow some headers/intro lines; require majority of date-like content lines prefixed
    date_mentioning = [l for l in content_lines if re.search(r'\b\d{4}\b', l)]
    bad = [l for l in date_mentioning if not iso_re.match(l)]
    if bad:
        return {'observed_followed': False,'confidence':'medium','reason':f'lines with dates not ISO-prefixed: {bad[:3]}','evidence_refs':[]}
    dates = [e[0][:10] for e in entries]
    sorted_ok = all(dates[i] <= dates[i+1] for i in range(len(dates)-1))
    if not sorted_ok:
        return {'observed_followed': False,'confidence':'high','reason':f'dates not ascending: {dates}','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':f'{len(entries)} entries ISO-prefixed and ascending','evidence_refs':[]}
