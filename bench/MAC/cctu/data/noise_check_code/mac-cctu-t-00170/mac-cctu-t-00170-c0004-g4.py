def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    _count_cultural_landmark_identifier = sum(1 for name in tool_names if name == 'cultural_landmark_identifier')
    if _count_cultural_landmark_identifier < 3:
        reasons.append('cultural_landmark_identifier' + ' call count below 3')
    _count_explorer_identifier = sum(1 for name in tool_names if name == 'explorer_identifier')
    if _count_explorer_identifier < 3:
        reasons.append('explorer_identifier' + ' call count below 3')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
