def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = text.splitlines()
    numbered = [l for l in lines if re.match(r'\s*\d+[\.|\)]\s+', l)]
    if len(numbered) < 1:
        return {'observed_followed': False, 'confidence':'high','reason':'no numbered incident log entries detected','evidence_refs':[]}
    date_re = re.compile(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4})', re.IGNORECASE)
    id_re = re.compile(r'([A-Z]{2,}[-_/ ]?\d+|#\s*\d+|\bID[:#\s-]+\S+|\b[A-Z0-9]{4,}\b)')
    ok = 0
    for l in numbered:
        head = l.split(':',1)[0] if ':' in l else l
        # Check prefix area (first ~120 chars) for both id and date
        prefix = l[:200]
        if date_re.search(prefix) and id_re.search(prefix):
            ok += 1
    if ok == len(numbered) and ok > 0:
        return {'observed_followed': True,'confidence':'high','reason':f'{ok} numbered entries each prefixed with id and date','evidence_refs':[]}
    if ok >= 1 and ok >= len(numbered)*0.8:
        return {'observed_followed': True,'confidence':'medium','reason':f'{ok}/{len(numbered)} entries match id+date prefix','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':f'only {ok}/{len(numbered)} numbered entries have id+date prefix','evidence_refs':[]}
