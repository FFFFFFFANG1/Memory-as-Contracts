import json
def evaluate(trace):
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable agent behavior', 'evidence_refs': []}
    ok = True
    evidence = []
    reasons = []
    try:
        parsed = json.loads(response.strip())
        if not isinstance(parsed, dict):
            ok = False
            reasons.append('response is not a JSON object')
    except Exception:
        ok = False
        reasons.append('response is not valid JSON')
    marks = ['**', '__', '`', '# ', '- ', '* ']
    if any(mark in response for mark in marks):
        ok = False
        reasons.append('format marker observed')
    if ok:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'observable behavior matched the generated check', 'evidence_refs': evidence}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons) or 'required behavior not observed', 'evidence_refs': evidence}
