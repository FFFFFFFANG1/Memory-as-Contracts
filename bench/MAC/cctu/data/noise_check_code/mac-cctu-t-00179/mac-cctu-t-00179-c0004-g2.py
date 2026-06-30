def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if not paragraphs:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no paragraphs', 'evidence_refs': []}
    first = paragraphs[0]
    words = re.findall(r"[A-Za-z'\-]+", first)
    wc = len(words)
    has_digits = bool(re.search(r'\d', first))
    if wc < 50:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'first paragraph has {wc} words (<50)', 'evidence_refs': [first[:120]]}
    if has_digits:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'first paragraph contains numeric findings', 'evidence_refs': [first[:120]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'opening paragraph has {wc} words and no digits', 'evidence_refs': [first[:120]]}
