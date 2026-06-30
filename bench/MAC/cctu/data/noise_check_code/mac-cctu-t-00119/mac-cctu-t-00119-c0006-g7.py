def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Look for a numeric confidence score sentence
    conf_pattern = re.compile(r'confidence[^.\n]*?(\d+(?:\.\d+)?)\s*%?', re.IGNORECASE)
    m = conf_pattern.search(text)
    if not m:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no numeric confidence score sentence found', 'evidence_refs': []}
    # Find commentary paragraph after the confidence sentence
    tail = text[m.end():]
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', tail) if p.strip()]
    long_para = any(len(p) >= 400 for p in paragraphs)
    if not long_para:
        # also try the whole tail length as a single paragraph fallback
        if len(tail.strip()) >= 400 and tail.strip():
            long_para = True
    if not long_para:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no analyst commentary paragraph >= 400 chars after confidence sentence', 'evidence_refs': [m.group(0)]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'found confidence score sentence and >=400 char commentary paragraph', 'evidence_refs': [m.group(0)]}
