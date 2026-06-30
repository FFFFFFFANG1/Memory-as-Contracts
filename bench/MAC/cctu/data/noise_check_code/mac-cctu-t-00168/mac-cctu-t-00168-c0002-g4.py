def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Single numeric value, no formatting (no commas, no units, no extra text)
    if re.fullmatch(r'-?\d+(?:\.\d+)?', resp):
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'final response is a single unformatted numeric value', 'evidence_refs': [resp]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response is not a single unformatted numeric value', 'evidence_refs': [resp[:120]]}
