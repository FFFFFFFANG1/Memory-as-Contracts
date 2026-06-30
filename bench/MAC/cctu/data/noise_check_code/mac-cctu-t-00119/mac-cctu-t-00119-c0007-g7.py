def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    names = [(tc.get('name') or '').lower() for tc in tcs]
    final = (trace.get('final_response') or '')
    low = final.lower()
    has_weight = any('weight_calculator' in n for n in names)
    has_fuel = any(('fuel_price_checker' in n) or ('merged_price_checker' in n) or ('oil_gas_price_predictor' in n) for n in names)
    mentions_fuel_price = bool(re.search(r'fuel\s*price|\$/?gal|per\s+gallon|price\s+per\s+gallon', low))
    cpm_pat = re.search(r'(cost[-\s]?per[-\s]?mile|\$\s*/\s*mile|per\s+mile|/mi\b|cents?\s*/?\s*mile)', low)
    if not mentions_fuel_price and not has_fuel:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No fuel price content detected; constraint may not apply.', 'evidence_refs': []}
    if not has_weight:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Fuel pricing discussed but weight_calculator was not invoked to supply the active vehicle weight profile.', 'evidence_refs': [{'tool_names': names}]}
    if not cpm_pat:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Response does not express fuel prices as cost-per-mile figures.', 'evidence_refs': [{'final_excerpt': final[:200]}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'weight_calculator used and response presents cost-per-mile derived from fuel prices.', 'evidence_refs': [{'tool_names': names}, {'match': cpm_pat.group(0)}]}
