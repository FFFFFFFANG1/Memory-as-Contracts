def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Split into paragraphs by blank lines
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if len(paragraphs) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'fewer than two paragraphs; cannot have opening summary and concluding ambassador', 'evidence_refs': [text[:120]]}
    first = paragraphs[0]
    last = paragraphs[-1]
    # First paragraph should be a single paragraph (no internal blank lines already ensured) and read like context summary
    diplomatic_terms = ['diplomat','diplomatic','relations','treaty','negotiat','tension','accord','embassy','foreign','ambassad','bilateral','dispute','incident','crisis']
    first_lower = first.lower()
    has_context = any(t in first_lower for t in diplomatic_terms)
    # Last should name an ambassador
    last_clean = last.strip().rstrip('.')
    # Look for 'Ambassador <Name>' pattern or ends with capitalized name preceded by ambassador reference
    amb_pattern = re.search(r'[Aa]mbassador\s+([A-Z][a-zA-Z\.\-]+(?:\s+[A-Z][a-zA-Z\.\-]+){0,3})', last)
    ends_with_name = False
    if amb_pattern:
        # Check that the ambassador mention is near the end
        match_end = amb_pattern.end()
        tail = last[match_end:].strip().strip('.')
        if len(tail) <= 40:
            ends_with_name = True
    followed = bool(has_context and ends_with_name)
    reason = f'has_context={has_context}, ends_with_ambassador={ends_with_name}, paragraphs={len(paragraphs)}'
    return {'observed_followed': followed, 'confidence': 'medium' if followed else 'medium', 'reason': reason, 'evidence_refs': [first[:120], last[-160:]]}
