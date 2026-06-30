def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    md_patterns = [r'^#{1,6}\s', r'\*\*[^*]+\*\*', r'(^|\s)\*[^*]+\*', r'__[^_]+__', r'`[^`]+`', r'^\s*[-*+]\s+', r'^\s*\d+\.\s+', r'\[[^\]]+\]\([^)]+\)', r'^>\s']
    md_hits = []
    for pat in md_patterns:
        if re.search(pat, resp, re.MULTILINE):
            md_hits.append(pat)
    words = re.findall(r"\b[\w'-]+\b", resp)
    wc = len(words)
    has_url = bool(re.search(r'https?://\S+', resp))
    in_range = 40 <= wc <= 60
    followed = (not md_hits) and in_range and has_url
    reasons = []
    if md_hits:
        reasons.append('markdown syntax detected: ' + ','.join(md_hits[:3]))
    if not in_range:
        reasons.append(f'word count {wc} outside 40-60')
    if not has_url:
        reasons.append('no inline URL found')
    if followed:
        reasons.append(f'plain text, {wc} words, URL present')
    return {'observed_followed': bool(followed), 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
