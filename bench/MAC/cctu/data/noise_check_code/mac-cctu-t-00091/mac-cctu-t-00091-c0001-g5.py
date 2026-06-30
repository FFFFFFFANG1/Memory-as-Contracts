def evaluate(trace):
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    ok = True
    evidence = []
    reasons = []
    marks = ['**', '__', '`', '# ', '- ', '* ']
    if not any(mark in response for mark in marks):
        ok = False
        reasons.append('format marker missing')
    if ok:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'observable behavior matched minimal check', 'evidence_refs': evidence}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons) or 'required behavior not observed', 'evidence_refs': evidence}
