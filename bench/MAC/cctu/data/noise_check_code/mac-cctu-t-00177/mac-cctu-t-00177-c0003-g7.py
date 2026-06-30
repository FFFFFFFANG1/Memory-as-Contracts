def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Find all percentage tokens
    pct_matches = re.findall(r'(-?\d+(?:\.\d+)?)\s*%', text)
    # Detect comparison cues
    comp_cues = re.search(r'\b(more than|less than|greater than|fewer than|higher than|lower than|compared to|versus|vs\.?|times as|times more|times fewer|increase|decrease|ratio|percent|percentage)\b', text, re.I)
    if not pct_matches and not comp_cues:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no quantitative comparisons detected', 'evidence_refs': []}
    bad = []
    for m in pct_matches:
        if '.' not in m:
            bad.append(m + '% (no decimal)')
        else:
            dec = m.split('.')[1]
            if len(dec) != 1:
                bad.append(m + '% (decimal places=' + str(len(dec)) + ')')
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'percentages not rounded to one decimal: ' + '; '.join(bad[:5]), 'evidence_refs': []}
    if comp_cues and not pct_matches:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'comparison language present but no percentage expressed', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'all percentages have one decimal place', 'evidence_refs': []}
