def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    geo_climate = {'climate_data_retriever','continent_locator','landmark_city_locator','rainforest_info_provider'}
    econ_indices = [c.get('index', i) for i, c in enumerate(calls) if c.get('name') == 'economic_data_retriever']
    geo_indices = [c.get('index', i) for i, c in enumerate(calls) if c.get('name') in geo_climate]
    order_ok = None
    if econ_indices and geo_indices:
        order_ok = min(econ_indices) < min(geo_indices)
    elif econ_indices and not geo_indices:
        order_ok = True
    elif not econ_indices and geo_indices:
        order_ok = False
    else:
        order_ok = None
    final = trace.get('final_response') or ''
    # Look for GDP mentions
    gdp_ok = None
    if re.search(r'GDP', final, re.IGNORECASE):
        # Find numeric figures associated with GDP/trillion
        # Pattern: number with exactly two decimals followed by 'trillion' or 'T USD'
        figures = re.findall(r'\$?\s*(\d+\.\d+)\s*(?:trillion|T\b)', final, re.IGNORECASE)
        if not figures:
            gdp_ok = False
        else:
            gdp_ok = all(len(f.split('.')[1]) == 2 for f in figures)
    if order_ok is None and gdp_ok is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No economic/GDP evidence found', 'evidence_refs': []}
    if order_ok is False:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Climate/geography tool called before economic_data_retriever', 'evidence_refs': []}
    if gdp_ok is False:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'GDP figures not in trillions with two decimal places', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Economic tool prioritized and/or GDP formatted correctly', 'evidence_refs': []}
