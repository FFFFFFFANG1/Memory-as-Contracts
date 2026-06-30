def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '')
    low = resp.lower()
    has_price = bool(re.search(r'\d', resp)) and ('price' in low or 'cost' in low or '€' in resp or 'eur' in low or 'usd' in low or '$' in resp)
    if not has_price:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No price quote detected in final response; cannot assess conversion.', 'evidence_refs': []}
    has_eur = ('eur' in low) or ('€' in resp)
    usd_pattern = re.search(r'(usd|us\$|\bU\.S\. dollars?\b|\$\s?\d)', resp, re.IGNORECASE)
    has_usd = bool(usd_pattern)
    if has_eur and not has_usd:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Final response shows EUR and omits USD values.', 'evidence_refs': ['final_response']}
    if has_usd:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Final response still contains USD price value.', 'evidence_refs': ['final_response']}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Price quoted but not converted to EUR.', 'evidence_refs': ['final_response']}
