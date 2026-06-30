def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no content', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*([-*+]|\d+\.)\s+')
    bullet_lines = [l for l in lines if bullet_re.match(l)]
    is_bullet_list = len(bullet_lines) >= 2 and len(bullet_lines) >= max(1, int(0.5 * len(lines)))
    # Find citations at end: look at trailing block
    # Citations could be URLs, [1] style, or 'Source:' lines
    tail = lines[-15:]
    citation_count = 0
    url_re = re.compile(r'https?://|www\.')
    bracket_re = re.compile(r'^\s*[\[\(]?\d+[\]\)\.]')
    src_re = re.compile(r'(?i)source|citation|reference')
    # Count citations anywhere near the end
    for l in tail:
        if url_re.search(l) or bracket_re.match(l) or src_re.search(l):
            citation_count += 1
    # Also try counting URLs total at end half
    end_half = '\n'.join(lines[len(lines)//2:])
    url_hits = len(url_re.findall(end_half))
    citation_count = max(citation_count, url_hits)
    has_citations = citation_count >= 5
    followed = is_bullet_list and has_citations
    reason = f'bullet_lines={len(bullet_lines)}/{len(lines)}, citations~={citation_count}'
    return {'observed_followed': followed, 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
