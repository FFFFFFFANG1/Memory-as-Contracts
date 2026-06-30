def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Check BibTeX entry pattern @type{key, ...}
    has_entry = bool(re.search(r'@\w+\s*\{', resp))
    fields = {}
    for fname in ['title','author','year','publisher']:
        m = re.search(r'(?im)^\s*' + fname + r'\s*=\s*[\{"\"]', resp)
        fields[fname] = bool(m)
    missing = [k for k,v in fields.items() if not v]
    # detect narrative sentences: lines outside braces that look like prose
    # heuristic: strip the bibtex block, see if leftover contains sentences
    bibtex_match = re.search(r'@\w+\s*\{.*\}', resp, re.DOTALL)
    leftover = resp
    if bibtex_match:
        leftover = (resp[:bibtex_match.start()] + resp[bibtex_match.end():]).strip()
    narrative = False
    if leftover:
        # sentence-like: contains words and ends with period/exclamation
        if re.search(r'[A-Za-z]{3,}.*[.!?]', leftover):
            narrative = True
        elif len(leftover.split()) > 3:
            narrative = True
    if not has_entry:
        return {'observed_followed': False,'confidence':'high','reason':'no BibTeX @entry found','evidence_refs':[]}
    if missing:
        return {'observed_followed': False,'confidence':'high','reason':'missing fields: '+','.join(missing),'evidence_refs':[]}
    if narrative:
        return {'observed_followed': False,'confidence':'medium','reason':'narrative text present outside BibTeX entry','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'BibTeX record with required fields and no narrative','evidence_refs':[]}
