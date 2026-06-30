def evaluate(trace):
    import re
    resp = trace.get('final_response')
    if resp is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    s = resp.strip() if isinstance(resp, str) else ''
    if not s:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Must be a single numeric figure: digits only, optional leading minus, optional single decimal point
    if re.fullmatch(r'-?\d+(\.\d+)?', s):
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'response is a single numeric figure with no prose/labels/punctuation', 'evidence_refs': [s]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'response is not a bare numeric figure', 'evidence_refs': [s[:120]]}
