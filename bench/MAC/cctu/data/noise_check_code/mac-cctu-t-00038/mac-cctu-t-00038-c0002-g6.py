def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    # Heuristic detection that individuals are being returned
    person_signals = ['president','minister','general','king','queen','leader','senator','chancellor','emperor','dictator','politician','commander']
    has_people = any(s in low for s in person_signals) or bool(re.search(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+', text))
    if not has_people:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no identifiable individuals in response', 'evidence_refs': []}
    dob = any(k in low for k in ['date of birth','born:','born on','dob','b. '])
    nat = 'nationality' in low or 'nationalit' in low
    aff_keys = ['affiliation','affiliations','party','organization','primary affiliation']
    aff = any(k in low for k in aff_keys)
    missing = [n for n,v in [('dob',dob),('nationality',nat),('affiliations',aff)] if not v]
    if not missing:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'DOB, nationality, and affiliations present', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'missing biographical fields: ' + ','.join(missing), 'evidence_refs': []}
