def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    low = text.lower()
    forecast_terms = ['forecast', 'predict', 'projection', 'will be', 'expected to', 'anticipate', 'outlook']
    forecast_idx = -1
    for t in forecast_terms:
        i = low.find(t)
        if i != -1 and (forecast_idx == -1 or i < forecast_idx):
            forecast_idx = i
    if forecast_idx == -1:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no forecast statement found to anchor ordering', 'evidence_refs': []}
    pre = low[:forecast_idx]
    has_texas = 'texas' in pre
    has_oil_or_gas = ('oil' in pre) or ('gas' in pre) or ('petroleum' in pre)
    five_year_patterns = [r'five[- ]year', r'5[- ]year', r'past five years', r'last five years', r'past 5 years', r'last 5 years', r'over (the )?(past|last) five', r'over (the )?(past|last) 5']
    has_five = any(re.search(p, pre) for p in five_year_patterns)
    historical_terms = ['historical', 'history', 'previously', 'prior', 'past', 'over the past', 'trend']
    has_hist = any(t in pre for t in historical_terms)
    followed = has_texas and has_oil_or_gas and has_five and has_hist
    reason = f'pre-forecast: texas={has_texas}, oil/gas={has_oil_or_gas}, five-year={has_five}, historical={has_hist}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
