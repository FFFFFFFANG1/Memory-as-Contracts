def evaluate(trace):
    import re
    tools = ['attraction_locator','biographical_data_search','cultural_geography_locator','facility_locator','historical_landmark_locator','historical_region_locator','hospital_survival_rate_analyzer','medical_research_center_locator','nearby_supplier_locator','supplier_hospital_locator']
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    stripped = resp.strip('`"\' .\n\t')
    if stripped in tools:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'final response is single tool name: {stripped}', 'evidence_refs': []}
    tokens = re.findall(r'[A-Za-z_]+', resp)
    if len(tokens) == 1 and tokens[0] in tools:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'single token tool name', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response is not a single tool name', 'evidence_refs': [resp[:120]]}
