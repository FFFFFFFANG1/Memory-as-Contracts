def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [ln for ln in response.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no content lines', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[.)])\s+(.*)$')
    bullet_lines = [ln for ln in lines if bullet_re.match(ln)]
    if not bullet_lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no outline/bullet structure detected; constraint may not apply', 'evidence_refs': []}
    non_bullets = [ln for ln in lines if not bullet_re.match(ln)]
    # allow headings like '# ...' only if they are themselves bullets? Treat any non-bullet line as prose violation
    if non_bullets:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'non-bullet prose lines present: ' + repr(non_bullets[:2]), 'evidence_refs': []}
    bad_punct = []
    for ln in bullet_lines:
        m = bullet_re.match(ln)
        text = m.group(2).rstrip()
        # strip trailing markdown like ** or * or backticks
        stripped = re.sub(r'[`*_\)\]]+$', '', text).rstrip()
        if stripped and stripped[-1] in '.!?;':
            bad_punct.append(ln)
    if bad_punct:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'bullet items have terminal punctuation: ' + repr(bad_punct[:2]), 'evidence_refs': []}
    # check for prose sentences inside bullet content (multiple sentences ending with .)
    for ln in bullet_lines:
        m = bullet_re.match(ln)
        text = m.group(2)
        # internal sentence punctuation suggests prose
        if re.search(r'[.!?]\s+[A-Z]', text):
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'prose sentence detected within bullet: ' + repr(ln), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all lines are bullets without terminal punctuation', 'evidence_refs': []}
