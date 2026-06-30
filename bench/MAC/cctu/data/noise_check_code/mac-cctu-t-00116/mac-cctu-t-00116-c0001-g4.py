def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    stripped = text.strip()
    reasons = []
    if len(stripped) > 80:
        reasons.append(f'length {len(stripped)} > 80 chars')
    md_patterns = [r'^#{1,6}\s', r'\*\*[^*]+\*\*', r'(^|\s)\*[^*]+\*', r'`[^`]+`', r'^\s*[-*+]\s', r'^\s*\d+\.\s', r'\[[^\]]+\]\([^)]+\)', r'^>\s']
    for p in md_patterns:
        if re.search(p, stripped, re.MULTILINE):
            reasons.append(f'markdown pattern {p!r}')
            break
    s = stripped.strip()
    if (s.startswith('{') and s.endswith('}')) or (s.startswith('[') and s.endswith(']')):
        reasons.append('looks like JSON')
    if '\n' in stripped:
        reasons.append('multiple lines / structured')
    sentence_terms = re.findall(r'[.!?]+(?:\s|$)', stripped)
    body = re.sub(r'[.!?]+\s*$', '', stripped)
    if re.search(r'[.!?]+\s+\S', body):
        reasons.append('more than one sentence')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'single sentence, {len(stripped)} chars, plain text', 'evidence_refs': []}
