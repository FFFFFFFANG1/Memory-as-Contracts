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
    required = ['astronomical_discovery_finder', 'concert_hall_locator']
    if not any(name in names or name in text_l for name in required):
        ok = False
        reasons.append('required named operation not observed')
    else:
        evidence.append({'type': 'tool_names', 'names': [name for name in required if name in names or name in text_l]})
    if ok:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'observable behavior matched the generated check', 'evidence_refs': evidence}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons) or 'required behavior not observed', 'evidence_refs': evidence}
