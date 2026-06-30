def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    low = text.lower()
    has_unesco = 'unesco' in low
    has_risk = bool(re.search(r'\b(low|medium|high)\b', low) and ('risk' in low or 'preservation' in low))
    if has_unesco and has_risk:
        return {'observed_followed': True, 'confidence':'medium','reason':'mentions UNESCO and preservation risk level','evidence_refs':[]}
    if not has_unesco and not has_risk:
        return {'observed_followed': False, 'confidence':'medium','reason':'no UNESCO citation or risk level','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':f'missing UNESCO={not has_unesco}, missing risk={not has_risk}','evidence_refs':[]}
