def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = [ln for ln in response.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no content lines', 'evidence_refs': []}
    reasons = []
    bullet_re = re.compile(r'^\s*([-*•+]|\d+[.)])\s+\S')
    non_bullet = [ln for ln in lines if not bullet_re.match(ln)]
    if non_bullet:
        reasons.append('non-bullet lines present: ' + repr(non_bullet[0])[:80])
    heading_lines = [ln for ln in lines if re.match(r'^\s*#{1,6}\s+', ln)]
    if heading_lines:
        reasons.append('heading detected: ' + repr(heading_lines[0])[:80])
    if re.search(r'\*\*[^*\n]+\*\*', response) or re.search(r'__[^_\n]+__', response):
        reasons.append('bold markdown present')
    terminal_punct = set('.!?;:,')
    bad_term = []
    for ln in lines:
        stripped = ln.rstrip()
        if stripped and stripped[-1] in terminal_punct:
            bad_term.append(stripped)
    if bad_term:
        reasons.append('terminal punctuation on line: ' + repr(bad_term[0])[:80])
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'plain-text bulleted list with no headings, bold, or terminal punctuation', 'evidence_refs': []}
