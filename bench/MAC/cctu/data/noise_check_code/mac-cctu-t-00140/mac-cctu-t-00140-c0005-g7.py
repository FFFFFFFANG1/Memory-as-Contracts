def evaluate(trace):
    import re
    resp = trace.get('final_response')
    if resp is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    text = resp.strip() if isinstance(resp, str) else ''
    if not text:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    if len(text) > 280:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'length {len(text)} > 280', 'evidence_refs': []}
    md_patterns = [r'\*\*[^*]+\*\*', r'(^|\s)\*[^*]+\*', r'(^|\s)_[^_]+_', r'`[^`]+`', r'^#{1,6}\s', r'^\s*[-*+]\s', r'\[[^\]]+\]\([^)]+\)', r'^>\s']
    for pat in md_patterns:
        if re.search(pat, text, re.MULTILINE):
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'markdown detected: {pat}', 'evidence_refs': []}
    tokens = text.split()
    if not tokens:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tokens', 'evidence_refs': []}
    last = tokens[-1].rstrip('.,!?;:')
    if not re.match(r'^#\w+', last):
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'does not end with hashtag: {last!r}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'within 280 chars, no markdown, ends with hashtag', 'evidence_refs': []}
