def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    eq_calls = [tc for tc in tool_calls if tc.get('name') == 'earthquake_event_retriever']
    # Detect if response references events at all
    has_event_ref = bool(re.search(r'earthquake|quake|event|magnitude|tremor', final, re.I))
    if not has_event_ref:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No event references detected in final response.', 'evidence_refs': []}
    # Look for lat/long annotations in response
    coord_pattern = re.compile(r'(-?\d{1,3}\.\d+)\s*[,\s]\s*(-?\d{1,3}\.\d+)')
    lat_kw = re.search(r'lat(itude)?', final, re.I)
    lon_kw = re.search(r'lon(g(itude)?)?', final, re.I)
    has_coords = bool(coord_pattern.search(final)) or (lat_kw and lon_kw)
    if not eq_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Response references events but earthquake_event_retriever was not called to retrieve coordinates.', 'evidence_refs': []}
    if not has_coords:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Events referenced without latitude/longitude annotations in response.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Events appear annotated with coordinates and earthquake_event_retriever was used.', 'evidence_refs': []}
