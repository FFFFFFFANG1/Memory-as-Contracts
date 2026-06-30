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
    _count_advanced_calculator = sum(1 for name in tool_names if name == 'advanced_calculator')
    if _count_advanced_calculator > 2:
        reasons.append('advanced_calculator' + ' call count ' + str(_count_advanced_calculator) + ' above 2')
    _count_historical_infrastructure_info = sum(1 for name in tool_names if name == 'historical_infrastructure_info')
    if _count_historical_infrastructure_info < 1:
        reasons.append('historical_infrastructure_info' + ' call count ' + str(_count_historical_infrastructure_info) + ' below 1')
    if _count_historical_infrastructure_info > 2:
        reasons.append('historical_infrastructure_info' + ' call count ' + str(_count_historical_infrastructure_info) + ' above 2')
    _count_historical_residence_finder = sum(1 for name in tool_names if name == 'historical_residence_finder')
    if _count_historical_residence_finder > 2:
        reasons.append('historical_residence_finder' + ' call count ' + str(_count_historical_residence_finder) + ' above 2')
    round_count = len(trajectory)
    if response.strip() and not response.rstrip().endswith('.'):
        reasons.append('response does not end with period')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
