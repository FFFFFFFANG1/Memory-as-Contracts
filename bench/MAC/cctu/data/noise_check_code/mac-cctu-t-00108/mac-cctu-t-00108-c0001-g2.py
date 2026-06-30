def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    length = len(resp)
    length_ok = length < 200
    md_patterns = [r'^#{1,6}\s', r'\*\*[^*]+\*\*', r'(^|\s)\*[^*\s][^*]*\*', r'__[^_]+__', r'(^|\s)_[^_\s][^_]*_', r'`[^`]+`', r'```', r'^\s*[-*+]\s+', r'^\s*\d+\.\s+', r'\[[^\]]+\]\([^)]+\)', r'^>\s']
    found = []
    for p in md_patterns:
        if re.search(p, resp, re.MULTILINE):
            found.append(p)
    md_ok = len(found) == 0
    followed = length_ok and md_ok
    reason = f'length={length} (<200:{length_ok}); markdown_found={found}'
    return {'observed_followed': followed, 'confidence': 'high', 'reason': reason, 'evidence_refs': []}
