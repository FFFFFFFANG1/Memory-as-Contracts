def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    words = re.findall(r"\S+", text)
    wc = len(words)
    md_patterns = [r'^#{1,6}\s', r'\*\*[^*]+\*\*', r'(?<!\*)\*[^*\n]+\*(?!\*)', r'`[^`]+`', r'^\s*[-*+]\s+', r'^\s*\d+\.\s+', r'\[[^\]]+\]\([^)]+\)', r'^>\s']
    md_hits = []
    for p in md_patterns:
        if re.search(p, text, re.MULTILINE):
            md_hits.append(p)
    over = wc >= 100
    if over and md_hits:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{wc} words and markdown markers {md_hits}', 'evidence_refs': []}
    if over:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'response has {wc} words (>=100)', 'evidence_refs': []}
    if md_hits:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'markdown markers found: {md_hits}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{wc} words, plain text', 'evidence_refs': []}
