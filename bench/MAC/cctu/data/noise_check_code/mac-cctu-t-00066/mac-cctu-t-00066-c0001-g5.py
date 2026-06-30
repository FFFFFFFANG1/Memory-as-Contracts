import json
def evaluate(trace):
    response = str(trace.get('final_response') or '')
    calls = trace.get(''.join(['tool', '_calls'])) or []
    if not response.strip() and not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    ok = True
    evidence = []
    reasons = []
    names = [str(c.get('name') or '') for c in calls if isinstance(c, dict)]
    text_l = response.lower()
    required = ['artist_relationship_finder']
    matched = [name for name in required if name in names or name in text_l]
    if not matched:
        ok = False
        reasons.append('named operation not observed')
    else:
        evidence.append({'type': 'operation_names', 'names': matched})
    try:
        parsed = json.loads(response.strip())
        if not isinstance(parsed, dict):
            ok = False
            reasons.append('not a JSON object')
    except Exception:
        ok = False
        reasons.append('invalid JSON')
    if ok:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'observable behavior matched minimal check', 'evidence_refs': evidence}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons) or 'required behavior not observed', 'evidence_refs': evidence}
