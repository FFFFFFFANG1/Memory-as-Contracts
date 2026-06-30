def evaluate(trace):
    text = trace.get('final_response')
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    non_ascii = [(i, ch) for i, ch in enumerate(text) if ord(ch) > 127]
    if non_ascii:
        sample = ''.join(ch for _, ch in non_ascii[:10])
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'found {len(non_ascii)} non-ASCII chars, e.g. {sample!r}', 'evidence_refs': [{'index': i, 'char': ch} for i, ch in non_ascii[:5]]}
    if any(ord(ch) < 32 and ch not in '\n\r\t' for ch in text):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'non-printable control char present', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all characters are printable ASCII', 'evidence_refs': []}
