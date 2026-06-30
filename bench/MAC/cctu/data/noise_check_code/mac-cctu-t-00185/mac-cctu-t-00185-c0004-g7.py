def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    low = text.lower()
    # find paragraphs separated by blank lines
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    vary_terms = ['vary', 'varies', 'differ', 'different sources', 'depending on', 'range']
    source_terms = ['source', 'sources', 'cited', 'reported']
    highest_terms = ['highest', 'largest', 'maximum', 'greatest', 'tallest']
    def has_any(s, terms):
        return any(t in s for t in terms)
    for p in paragraphs:
        pl = p.lower()
        if has_any(pl, vary_terms) and has_any(pl, source_terms) and has_any(pl, highest_terms):
            return {'observed_followed': True, 'confidence': 'high', 'reason': 'Found disclaimer paragraph mentioning variation by source and highest cited value', 'evidence_refs': []}
    # fallback: check whole text contains all signals
    if has_any(low, vary_terms) and has_any(low, source_terms) and has_any(low, highest_terms):
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Disclaimer signals present but not isolated in a single paragraph', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Missing disclaimer about source variation and highest cited figure', 'evidence_refs': []}
