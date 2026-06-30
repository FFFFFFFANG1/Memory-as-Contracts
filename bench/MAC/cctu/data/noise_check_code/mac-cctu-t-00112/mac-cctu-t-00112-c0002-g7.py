def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '')
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Look for casualty figure pattern
    casualty_pat = re.compile(r'(casualt(?:y|ies)|killed|died|deaths?|fatalit(?:y|ies)|injured)[^\n.]*?(\d[\d,]*)', re.IGNORECASE)
    m = casualty_pat.search(resp)
    if not m:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no casualty figure detected; cannot judge dedication requirement','evidence_refs':[]}
    # Detect memorial week context
    memorial_terms = ['memorial week','remembrance week','commemoration week','memorial day','remembrance day','observance week']
    has_memorial = any(t in resp.lower() for t in memorial_terms)
    if not has_memorial:
        return {'observed_followed': None,'confidence':'unknown','reason':'no clear memorial-week context in trace','evidence_refs':[]}
    # Check for a dedication sentence after the casualty figure
    tail = resp[m.end():].strip()
    # Take first sentence after
    sent_match = re.match(r'\s*([^.!?\n]+[.!?])', tail)
    if not sent_match:
        return {'observed_followed': False,'confidence':'medium','reason':'no sentence follows casualty figure','evidence_refs':[m.group(0)]}
    sent = sent_match.group(1).strip()
    dedication_keywords = ['dedicat','memory','honor','honour','remember','tribute','commemor','in loving','rest in peace','never forget']
    if any(k in sent.lower() for k in dedication_keywords):
        return {'observed_followed': True,'confidence':'medium','reason':'dedication sentence follows casualty figure','evidence_refs':[sent]}
    return {'observed_followed': False,'confidence':'medium','reason':'sentence after casualty figure lacks dedication language','evidence_refs':[sent]}
