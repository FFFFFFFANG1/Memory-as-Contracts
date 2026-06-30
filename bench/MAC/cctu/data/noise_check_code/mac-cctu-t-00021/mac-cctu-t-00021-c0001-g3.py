def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_historical_agreement_finder = sum(1 for name in tool_names if name == 'historical_agreement_finder')
    if _count_historical_agreement_finder < 2:
        reasons.append('historical_agreement_finder' + ' call count ' + str(_count_historical_agreement_finder) + ' below 2')
    _count_historical_event_analyzer = sum(1 for name in tool_names if name == 'historical_event_analyzer')
    if _count_historical_event_analyzer < 2:
        reasons.append('historical_event_analyzer' + ' call count ' + str(_count_historical_event_analyzer) + ' below 2')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
