def evaluate(trace):
    response = str(trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    if not response.strip() and not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable agent behavior', 'evidence_refs': []}
    ok = True
    evidence = []
    reasons = []
    names = [str(c.get('name') or '') for c in calls if isinstance(c, dict)]
    text_l = response.lower()
    if not names:
        ok = False
        reasons.append('no tool usage observed')
    marks = ['**', '__', '`', '# ', '- ', '* ']
    if any(mark in response for mark in marks):
        ok = False
        reasons.append('format marker observed')
    if ok:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'observable behavior matched the generated check', 'evidence_refs': evidence}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons) or 'required behavior not observed', 'evidence_refs': evidence}
