def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    quantitative = {'historical_road_length_calculator', 'waterfall_volume_calculator', 'population_data_retriever'}
    scoping_violations = []
    quant_seen = False
    for i, c in enumerate(calls):
        name = c.get('name') or c.get('tool_name') or ''
        if name in quantitative:
            quant_seen = True
            break
        if name != 'historical_figure_identifier':
            scoping_violations.append((i, name))
    if not quant_seen and not scoping_violations:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No quantitative tool invoked; scoping phase boundary unclear but no non-identifier tool ran first', 'evidence_refs': [c.get('name','') for c in calls]}
    if scoping_violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Non-identifier tool(s) used during scoping before quantitative tools: {scoping_violations}', 'evidence_refs': [str(v) for v in scoping_violations]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Only historical_figure_identifier used during scoping before quantitative tools', 'evidence_refs': [c.get('name','') for c in calls]}
