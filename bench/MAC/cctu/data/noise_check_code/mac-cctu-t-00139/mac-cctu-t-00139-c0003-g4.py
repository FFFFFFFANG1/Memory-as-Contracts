def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    _count_volcano_activity_analyzer = sum(1 for name in tool_names if name == 'volcano_activity_analyzer')
    if _count_volcano_activity_analyzer < 1:
        reasons.append('volcano_activity_analyzer' + ' call count below 1')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
