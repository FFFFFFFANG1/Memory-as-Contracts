def evaluate(trace):
    allowed_initial = {'poetry_theme_search','literary_setting_search_v2'}
    geo_tools = {'geographical_area_calculator','historical_residence_finder','historical_visit_locator','landmark_info_retriever','official_residence_locator','urban_forest_locator'}
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    seen_literary = False
    for i, c in enumerate(calls):
        name = c.get('name') or c.get('tool_name') or ''
        if name in allowed_initial:
            seen_literary = True
            continue
        if name in geo_tools:
            if not seen_literary:
                return {'observed_followed': False, 'confidence': 'high', 'reason': f'Geographic tool {name} called at index {i} before any literary scoping tool', 'evidence_refs': [{'tool_index': i, 'tool_name': name}]}
            else:
                return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Geographic lookup deferred until after literary scoping tool used', 'evidence_refs': [{'tool_index': i, 'tool_name': name}]}
        else:
            if not seen_literary:
                return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Initial scoping used non-literary tool {name} before literary anchors', 'evidence_refs': [{'tool_index': i, 'tool_name': name}]}
    if seen_literary:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Initial scoping restricted to literary tools; no premature geographic lookups', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No literary scoping tool was used in initial phase', 'evidence_refs': []}
