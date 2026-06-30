def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty final response', 'evidence_refs': []}
    reasons = []
    if len(response) > 200:
        reasons.append('length ' + str(len(response)) + ' exceeds 200 chars')
    lines = [ln for ln in response.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no content lines', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*([\-\*\+\u2022\u25E6\u25AA\u25CF]|\d+[\.\)])\s+')
    non_bullet = [ln for ln in lines if not bullet_re.match(ln)]
    if non_bullet:
        reasons.append('non-bullet line present: ' + repr(non_bullet[0][:60]))
    delimiter_keywords = ['first','second','third','fourth','finally','lastly','next','then','furthermore','moreover','however','additionally','firstly','secondly','thirdly']
    low = response.lower()
    found_delims = []
    for kw in delimiter_keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', low):
            found_delims.append(kw)
    if found_delims:
        reasons.append('delimiter keywords found: ' + ','.join(found_delims))
    term_punct = set('.!?;:,')
    bad_term = []
    for ln in lines:
        stripped = ln.rstrip()
        if stripped and stripped[-1] in term_punct:
            bad_term.append(stripped[-20:])
    if bad_term:
        reasons.append('terminating punctuation on line(s): ' + repr(bad_term[0]))
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'bullets only, <=200 chars, no delimiter keywords, no terminating punctuation', 'evidence_refs': []}
