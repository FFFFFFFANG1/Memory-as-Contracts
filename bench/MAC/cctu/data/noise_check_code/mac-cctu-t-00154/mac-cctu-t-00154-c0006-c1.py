def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_population_estimator = sum(1 for name in tool_names if name == 'population_estimator')
    if _count_population_estimator < 1:
        reasons.append('population_estimator' + ' call count ' + str(_count_population_estimator) + ' below 1')
    _count_river_length_calculator = sum(1 for name in tool_names if name == 'river_length_calculator')
    if _count_river_length_calculator < 1:
        reasons.append('river_length_calculator' + ' call count ' + str(_count_river_length_calculator) + ' below 1')
    round_count = len(trajectory)
    if response.strip() and not response.rstrip().endswith('.'):
        reasons.append('response does not end with period')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
