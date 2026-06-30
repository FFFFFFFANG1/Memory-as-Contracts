def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    low = text.lower()
    gas_terms = ['natural gas','natural-gas','nat gas','gas price']
    mentions_gas = any(t in low for t in gas_terms)
    if not mentions_gas:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No natural-gas price summary detected in final response.', 'evidence_refs': []}
    eur_mwh_patterns = [r'eur\s*/\s*mwh', r'€\s*/\s*mwh', r'euros?\s+per\s+megawatt[- ]?hour', r'eur\s*per\s*mwh']
    has_eur_mwh = any(re.search(p, low) for p in eur_mwh_patterns)
    has_ttf = 'ttf' in low
    has_front_month = ('front-month' in low) or ('front month' in low)
    followed = has_eur_mwh and has_ttf and has_front_month
    reason = f'gas_mentioned=True, eur_per_mwh={has_eur_mwh}, ttf={has_ttf}, front_month={has_front_month}'
    return {'observed_followed': bool(followed), 'confidence': 'high' if followed else 'medium', 'reason': reason, 'evidence_refs': []}
