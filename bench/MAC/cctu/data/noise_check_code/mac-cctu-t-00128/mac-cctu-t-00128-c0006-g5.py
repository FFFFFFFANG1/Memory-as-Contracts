def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = text.lower()
    has_meters = bool(re.search(r'\b\d+(?:\.\d+)?\s*(m|meter|meters|metre|metres)\b', low))
    has_feet = bool(re.search(r'\b\d+(?:\.\d+)?\s*(ft|feet|foot)\b', low))
    mentions_depth = ('depth' in low) or has_meters or has_feet
    if not mentions_depth:
        return {'observed_followed': None, 'confidence':'low','reason':'no depth content detected; constraint may not apply','evidence_refs':[]}
    advisory = ('sea-ice' in low or 'sea ice' in low) and ('advisor' in low or 'coverage' in low or 'warning' in low or 'caution' in low)
    ok = has_meters and has_feet and advisory
    return {'observed_followed': bool(ok), 'confidence':'medium','reason': f'meters={has_meters} feet={has_feet} advisory={advisory}','evidence_refs':[]}
