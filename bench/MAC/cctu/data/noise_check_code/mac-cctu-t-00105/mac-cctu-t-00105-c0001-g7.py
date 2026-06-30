def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Look at the last paragraph
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', resp) if p.strip()]
    if not paragraphs:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no paragraphs', 'evidence_refs': []}
    last = paragraphs[-1].lower()
    has_approx = any(t in last for t in ['approximate', 'approximation', 'estimate', 'estimat'])
    has_unverif = any(t in last for t in ['unverifiable', 'unverified', 'cannot be verified', 'not verifiable', 'difficult to verify'])
    mentions_deaths = any(t in last for t in ['death toll', 'death tolls', 'historical death', 'casualt', 'fatalit'])
    if has_approx and has_unverif and mentions_deaths:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'final paragraph contains disclaimer about approximate and unverifiable death tolls', 'evidence_refs': []}
    if (has_approx or has_unverif) and mentions_deaths:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'partial disclaimer language present in final paragraph', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'final paragraph lacks disclaimer about approximate/unverifiable death tolls', 'evidence_refs': []}
