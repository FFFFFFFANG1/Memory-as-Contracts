import re
def evaluate(trace):
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    iso_pat = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
    iso_year = re.compile(r'\b\d{4}\b')
    # Detect non-ISO date patterns
    non_iso_patterns = [
        r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        r'\b\d{1,2}-\d{1,2}-\d{4}\b',
        r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
    ]
    bad = []
    for p in non_iso_patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            bad.append(m.group(0))
    has_iso = bool(iso_pat.search(text)) or bool(iso_year.search(text))
    if not has_iso and not bad:
        return {'observed_followed': None,'confidence':'unknown','reason':'no dates detected','evidence_refs':[]}
    # Citation tag heuristic: [..], (source:..), [^..], <ref>, [n]
    cite_pat = re.compile(r'(\[[^\]]+\]|\(source[^)]*\)|\(cite[^)]*\)|\(ref[^)]*\)|<ref[^>]*>)', re.IGNORECASE)
    cites = cite_pat.findall(text)
    if bad:
        return {'observed_followed': False,'confidence':'high','reason':f'non-ISO date forms found: {bad[:3]}','evidence_refs':bad[:3]}
    if not cites:
        return {'observed_followed': False,'confidence':'medium','reason':'no citation tags detected for facts','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'ISO dates present and citation tags found','evidence_refs':cites[:3]}
