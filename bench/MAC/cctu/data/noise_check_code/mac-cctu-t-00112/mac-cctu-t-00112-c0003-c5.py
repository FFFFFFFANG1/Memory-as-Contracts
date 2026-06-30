def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    casualty_terms = r'(killed|deaths?|casualt(?:y|ies)|injured|fatalit(?:y|ies)|wounded|dead|missing|victims?)'
    # Find sentences/segments containing a number adjacent to casualty terms
    findings = []
    for m in re.finditer(r'([^.\n]*?\b\d[\d,\.]*\b[^.\n]*?)(?=[.\n]|$)', text):
        seg = m.group(1)
        if re.search(casualty_terms, seg, re.I):
            findings.append(seg.strip())
    if not findings:
        return {'observed_followed': None,'confidence':'low','reason':'no casualty figures detected','evidence_refs':[]}
    # Archive identifier heuristic: bracketed/parenthesized token, or ALLCAPS code, or prefix like 'ARCHIVE:' before the number
    archive_pat = re.compile(r'(\[[^\]]+\]|\([^)]+\)|\b[A-Z]{2,}[-_/0-9A-Z]*\b\s*[:\-]|\b[A-Z][A-Za-z]+ Archive\b|\bArchive[^:]*:)')
    missing = []
    for seg in findings:
        # look at substring before the number
        nm = re.search(r'\d[\d,\.]*', seg)
        if not nm:
            continue
        prefix = seg[:nm.start()]
        if not archive_pat.search(prefix):
            missing.append(seg)
    # Aggregate sum detection
    agg_pat = re.compile(r'\b(total|sum|combined|overall|aggregate|grand total|altogether|in all)\b', re.I)
    agg_hits = []
    for seg in findings:
        if agg_pat.search(seg):
            agg_hits.append(seg)
    if missing or agg_hits:
        reason = ''
        if missing:
            reason += f'{len(missing)} casualty figure(s) lack archive prefix. '
        if agg_hits:
            reason += f'{len(agg_hits)} aggregate sum reference(s) present.'
        return {'observed_followed': False,'confidence':'medium','reason':reason.strip(),'evidence_refs': (missing+agg_hits)[:3]}
    return {'observed_followed': True,'confidence':'medium','reason':'All casualty figures appear prefixed with an archive identifier and no aggregate sums detected.','evidence_refs': findings[:3]}
