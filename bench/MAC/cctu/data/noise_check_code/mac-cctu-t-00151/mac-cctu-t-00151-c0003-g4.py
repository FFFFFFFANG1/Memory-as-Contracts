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
    if tool_count > 10:
        reasons.append('tool call count {tool_count} above 10')
    round_count = len(trajectory)
    if response.strip() and not response.rstrip().endswith('.'):
        reasons.append('response does not end with period')
    if 'eu' not in response.lower():
        reasons.append('eu' + ' not mentioned in response')
    if 'un' not in response.lower():
        reasons.append('un' + ' not mentioned in response')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
