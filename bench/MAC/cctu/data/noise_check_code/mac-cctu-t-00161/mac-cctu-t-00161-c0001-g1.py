def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    words = re.findall(r'\S+', resp)
    wc = len(words)
    if wc >= 100:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'word count {wc} not under 100', 'evidence_refs': []}
    md_patterns = [r'^#{1,6}\s', r'\*\*', r'__', r'```', r'`[^`]+`', r'^\s*[-*+]\s', r'^\s*\d+\.\s', r'\[[^\]]+\]\([^)]+\)']
    for pat in md_patterns:
        if re.search(pat, resp, re.MULTILINE):
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'markdown formatting detected: {pat}', 'evidence_refs': []}
    lines = [l for l in resp.strip().splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no lines', 'evidence_refs': []}
    last = lines[-1].strip()
    if not re.fullmatch(r'[-+]?\$?\d[\d,]*(\.\d+)?%?', last):
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'final line not numeric only: {last!r}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{wc} words, plain text, numeric final line', 'evidence_refs': []}
