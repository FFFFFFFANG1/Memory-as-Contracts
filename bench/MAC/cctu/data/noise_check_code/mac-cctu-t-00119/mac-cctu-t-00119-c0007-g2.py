def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    low = text.lower()
    # Check euros per MWh unit
    unit_patterns = [r'eur\s*/\s*mwh', r'€\s*/\s*mwh', r'euros?\s*per\s*mwh', r'euro\s*/\s*mwh']
    unit_ok = any(re.search(p, low) for p in unit_patterns)
    # European hub references
    hubs = ['ttf','nbp','peg','the ','psv','cegh','ztp','zee','zeebrugge','ncg','gaspool','vtp','trs','pvb','nl ttf','title transfer facility','national balancing point','pegas','etf','baumgarten']
    found = set()
    for h in hubs:
        if h.strip() in low:
            found.add(h.strip())
    hub_ok = len(found) >= 2
    followed = unit_ok and hub_ok
    reason = f'unit_ok={unit_ok}, hubs_found={sorted(found)}'
    return {'observed_followed': bool(followed), 'confidence': 'medium' if followed else 'medium', 'reason': reason, 'evidence_refs': []}
