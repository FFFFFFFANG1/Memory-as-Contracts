def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    reasons = []
    # numbered markdown list: lines starting with '1.', '2.' etc.
    numbered = re.findall(r'(?m)^\s*\d+\.\s+', response)
    if len(numbered) < 1:
        reasons.append('no numbered markdown list items')
    # required headings
    required = ['Event', 'Confirmed Casualties', 'Source Tool']
    missing = [h for h in required if h.lower() not in response.lower()]
    if missing:
        reasons.append('missing headings: ' + ', '.join(missing))
    # markdown heading markers (#, **, or similar) should be present for headings
    has_md_heading = bool(re.search(r'(\*\*|__|^#+\s|^\s*-\s)', response, re.MULTILINE))
    if not has_md_heading:
        reasons.append('no markdown heading/formatting markers')
    # forbid computed date gaps: look for phrases like 'days', 'date gap', 'gap of', 'X days between'
    gap_patterns = [r'date\s*gap', r'gap\s+of\s+\d+', r'\b\d+\s+days?\s+(between|since|after|before|apart)', r'days?\s+elapsed', r'time\s+gap']
    for pat in gap_patterns:
        if re.search(pat, response, re.IGNORECASE):
            reasons.append('contains computed date gap: ' + pat)
            break
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'numbered markdown list with required headings; no date gaps detected', 'evidence_refs': []}
