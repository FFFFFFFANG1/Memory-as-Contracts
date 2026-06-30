def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Strip trailing punctuation for sentence count
    # Count sentence terminators inside the text (not just trailing)
    inner = resp.rstrip('.!?').strip()
    terminators = re.findall(r'[.!?]+(?:\s|$)', resp)
    sentence_count = len([t for t in terminators if t.strip()])
    if sentence_count == 0:
        sentence_count = 1
    # Also reject if multiple lines of content
    nonempty_lines = [l for l in resp.splitlines() if l.strip()]
    if len(nonempty_lines) > 1 or sentence_count > 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'response has {sentence_count} sentences / {len(nonempty_lines)} lines, not single short sentence', 'evidence_refs': [resp[:200]]}
    # Must contain a number
    has_number = bool(re.search(r'\d', resp))
    if not has_number:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no supporting number present', 'evidence_refs': [resp[:200]]}
    # Short: cap at ~30 words
    word_count = len(resp.split())
    if word_count > 30:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'response has {word_count} words, not condensed/short', 'evidence_refs': [resp[:200]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'single short sentence ({word_count} words) with number present', 'evidence_refs': [resp[:200]]}
