def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    geographic = {'distribution_center_locator','famous_peak_identifier','ferry_locator','individual_location_finder','nearby_forest_locator','rural_area_feature_locator','university_location_finder','wood_sourcing_locator'}
    anchor = 'musician_instrument_finder'
    first_anchor_idx = None
    first_geo_idx = None
    for i, c in enumerate(calls):
        name = c.get('name')
        if name == anchor and first_anchor_idx is None:
            first_anchor_idx = i
        if name in geographic and first_geo_idx is None:
            first_geo_idx = i
    if first_geo_idx is None and first_anchor_idx is None:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Neither anchor nor geographic tools invoked', 'evidence_refs': []}
    if first_anchor_idx is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'musician_instrument_finder never called before geographic tool', 'evidence_refs': [{'index': first_geo_idx, 'name': calls[first_geo_idx].get('name')}]}
    if first_geo_idx is not None and first_geo_idx < first_anchor_idx:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Geographic tool called before musician_instrument_finder', 'evidence_refs': [{'index': first_geo_idx, 'name': calls[first_geo_idx].get('name')}, {'index': first_anchor_idx, 'name': anchor}]}
    if calls[0].get('name') != anchor:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'First tool call was not musician_instrument_finder', 'evidence_refs': [{'index': 0, 'name': calls[0].get('name')}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'musician_instrument_finder invoked first, before any geographic tool', 'evidence_refs': [{'index': first_anchor_idx, 'name': anchor}]}
