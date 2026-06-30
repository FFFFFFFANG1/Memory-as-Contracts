def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    if len(resp) > 200:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'response is {len(resp)} chars, exceeds 200', 'evidence_refs': []}
    if re.search(r'\n\s*\n', resp):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response contains multiple paragraphs', 'evidence_refs': []}
    reasoning_markers = [r'\bstep\s*\d', r'\bfirst,?\s+i\b', r'\blet me think', r'\breasoning:', r'\bthought:', r'\bchain of thought', r'\bthinking:', r'<think', r'\banalysis:']
    low = resp.lower()
    for pat in reasoning_markers:
        if re.search(pat, low):
            return {'observed_followed': False, 'confidence': 'medium', 'reason': f'response contains reasoning marker matching {pat}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'single paragraph, {len(resp)} chars, no reasoning markers', 'evidence_refs': []}
