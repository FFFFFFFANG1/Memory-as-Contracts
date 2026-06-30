def evaluate(trace):
    tools = ['architectural_marvel_locator','biographical_information_retriever','celestial_body_surface_calculator','city_area_calculator','element_discovery_info','literary_reference_tool','mineral_finder','natural_feature_locator','species_discovery_finder','subterranean_mine_locator','vehicle_specifications_retriever']
    resp = (trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    invoked = [c.get('name') for c in calls if c.get('name') in tools]
    missing = [t for t in tools if t not in resp]
    if invoked:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Invoked data-retrieval tools: {invoked}', 'evidence_refs': []}
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Response missing tools: {missing}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'All tools enumerated and no tool calls invoked', 'evidence_refs': []}
