def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    word_count = len(text.split())
    md_patterns = [r'^#{1,6}\s', r'\*\*[^*]+\*\*', r'(^|\s)\*[^*\s][^*]*\*', r'`[^`]+`', r'^```', r'^\s*[-*+]\s', r'^\s*\d+\.\s', r'\[[^\]]+\]\([^)]+\)', r'^>\s']
    md_hits = []
    for p in md_patterns:
        if re.search(p, text, re.MULTILINE):
            md_hits.append(p)
    too_long = word_count >= 150
    has_md = len(md_hits) > 0
    followed = (not too_long) and (not has_md)
    reasons = []
    reasons.append(f'word_count={word_count}')
    if too_long: reasons.append('exceeds 150 words')
    if has_md: reasons.append(f'markdown patterns found: {md_hits}')
    return {'observed_followed': followed, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
