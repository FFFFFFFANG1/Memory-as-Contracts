def evaluate(trace):
    text = trace.get('final_response')
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    non_ascii = [(i, ch) for i, ch in enumerate(text) if ord(ch) > 127]
    if non_ascii:
        sample = ''.join(ch for _, ch in non_ascii[:10])
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found {len(non_ascii)} non-ASCII character(s): {sample!r}', 'evidence_refs': [{'type':'final_response_chars','positions':[i for i,_ in non_ascii[:10]]}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Final response is pure 7-bit ASCII', 'evidence_refs': []}
