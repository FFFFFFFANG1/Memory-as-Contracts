def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Empty content', 'evidence_refs': []}
    # Look for an integer line and a justification sentence
    int_line_idx = None
    for i, l in enumerate(lines):
        if re.fullmatch(r'\d+', l):
            int_line_idx = i
            break
    if int_line_idx is None:
        # Maybe single line with integer then sentence
        m = re.match(r'^(\d+)[\.\:\s\-—]+(.+)$', lines[0])
        if m and len(lines) == 1:
            justification = m.group(2).strip()
            sentences = re.split(r'(?<=[.!?])\s+', justification)
            sentences = [s for s in sentences if s.strip()]
            if len(sentences) == 1:
                return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Integer with one-sentence justification on one line', 'evidence_refs': [lines[0]]}
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Justification not a single sentence', 'evidence_refs': [justification]}
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No integer count found', 'evidence_refs': lines[:3]}
    # Check no per-species breakdown lines before integer
    breakdown_pattern = re.compile(r'^[\-\*\u2022]|:\s*\d+|\d+\s*$')
    pre = lines[:int_line_idx]
    bad = [l for l in pre if re.search(r':\s*\d+', l) or re.match(r'^[\-\*\u2022]', l)]
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Per-species breakdown lines detected', 'evidence_refs': bad[:3]}
    post = lines[int_line_idx+1:]
    if not post:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No justification after integer', 'evidence_refs': [lines[int_line_idx]]}
    justification = ' '.join(post)
    # Check for breakdown lines after
    bad_post = [l for l in post if re.search(r':\s*\d+', l) or re.match(r'^[\-\*\u2022]', l)]
    if bad_post:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Per-species breakdown after integer', 'evidence_refs': bad_post[:3]}
    sentences = re.split(r'(?<=[.!?])\s+', justification.strip())
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) != 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Justification has {len(sentences)} sentences', 'evidence_refs': sentences[:3]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Single integer followed by one-sentence justification', 'evidence_refs': [lines[int_line_idx], sentences[0]]}
