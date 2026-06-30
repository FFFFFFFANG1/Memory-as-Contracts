def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Empty final response', 'evidence_refs': []}
    # Count sentence terminators
    # Strip trailing punctuation for counting
    body = resp.rstrip()
    # Find sentence-ending punctuation occurrences
    terminators = re.findall(r'[.!?]+', body)
    # Remove a single trailing terminator
    core = re.sub(r'[.!?]+\s*$', '', body)
    inner_terms = re.findall(r'[.!?]', core)
    if inner_terms:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Multiple sentences detected: {len(inner_terms)+1}', 'evidence_refs': [resp[:120]]}
    # Check for reasoning markers / list markers / newlines
    if '\n' in resp.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Multi-line response suggests intermediate reasoning', 'evidence_refs': [resp[:120]]}
    lower = resp.lower()
    reasoning_markers = ['because', 'therefore', 'first,', 'then,', 'step ', 'reasoning', 'let me', 'i think', 'analysis', ':', ';', '- ', '* ']
    hits = [m for m in reasoning_markers if m in lower]
    if hits:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Possible reasoning/list markers: {hits}', 'evidence_refs': [resp[:160]]}
    # Should be declarative (not a question)
    if resp.rstrip().endswith('?'):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Not declarative (ends with ?)', 'evidence_refs': [resp[:120]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Single declarative sentence without visible reasoning', 'evidence_refs': [resp[:160]]}
