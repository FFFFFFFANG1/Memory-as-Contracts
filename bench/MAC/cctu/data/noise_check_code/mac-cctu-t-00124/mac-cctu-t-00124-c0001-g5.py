def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # find numeric timeline mentions (numbers followed by 'day' or 'days')
    days_matches = re.findall(r'\b\d+\s*days?\b', text, re.IGNORECASE)
    iso_matches = re.findall(r'\b\d{4}-\d{2}-\d{2}\b', text)
    # check for any numerical timeline-ish content at all
    has_numbers = bool(re.search(r'\b\d+\b', text))
    if not has_numbers:
        return {'observed_followed': None,'confidence':'unknown','reason':'no numerical content found','evidence_refs':[]}
    # narrative paragraph: at least one sentence-like structure
    has_narrative = bool(re.search(r'[A-Za-z][^\n.!?]{30,}[.!?]', text))
    if days_matches and iso_matches and has_narrative:
        return {'observed_followed': True,'confidence':'high','reason':f'found {len(days_matches)} day expressions and {len(iso_matches)} ISO dates within narrative','evidence_refs':[]}
    missing = []
    if not days_matches: missing.append('days expression')
    if not iso_matches: missing.append('ISO 8601 date')
    if not has_narrative: missing.append('narrative paragraph')
    return {'observed_followed': False,'confidence':'high','reason':'missing: '+', '.join(missing),'evidence_refs':[]}
