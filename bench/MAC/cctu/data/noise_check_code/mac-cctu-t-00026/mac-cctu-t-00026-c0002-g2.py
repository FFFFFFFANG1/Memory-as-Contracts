import json
def evaluate(trace):
    response = str(trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    if not response.strip() and not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    ok = True
    evidence = []
    reasons = []
    names = [str(c.get('name') or '') for c in calls if isinstance(c, dict)]
    text_l = response.lower()
    if not names:
        ok = False
        reasons.append('operation not observed')
    try:
        parsed = json.loads(response.strip())
        if not isinstance(parsed, dict):
            ok = False
            reasons.append('not a JSON object')
    except Exception:
        ok = False
        reasons.append('invalid JSON')
    marks = ['**', '__', '`', '# ', '- ', '* ']
    if not any(mark in response for mark in marks):
        ok = False
        reasons.append('format marker missing')
    if ok:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'observable behavior matched minimal check', 'evidence_refs': evidence}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons) or 'required behavior not observed', 'evidence_refs': evidence}
