def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = text.splitlines()
    prose_lines = []
    structured_idx = None
    struct_pat = re.compile(r'^\s*(([-*+]\s)|(\d+[\.)]\s)|(#+\s)|(\|)|(```)|(>\s)|(\{)|(\[))')
    for i, ln in enumerate(lines):
        if struct_pat.match(ln):
            structured_idx = i
            break
        prose_lines.append(ln)
    prose_block = []
    for ln in prose_lines:
        if ln.strip() == '' and prose_block:
            break
        if ln.strip():
            prose_block.append(ln.strip())
    if not prose_block:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no prose paragraph before structured content', 'evidence_refs': [text[:120]]}
    paragraph = ' '.join(prose_block)
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', paragraph) if s.strip()]
    n = len(sentences)
    if n == 0:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no sentences detected in opening prose', 'evidence_refs': [paragraph[:120]]}
    if n > 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'opening prose has {n} sentences (>3)', 'evidence_refs': [paragraph[:200]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'opening prose paragraph has {n} sentence(s) before structured content', 'evidence_refs': [paragraph[:200]]}
