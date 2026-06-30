def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    word_count = len(response.split())
    if word_count == 0:
        reasons.append('response text missing')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    called = {name for name in tool_names if name}
    required_tools = ['historical_hemisphere_locator_v2', 'historical_location_finder']
    missing = sorted(t for t in required_tools if t not in called)
    if missing:
        reasons.append('required tools not called: ' + ', '.join(missing[:5]))
    allowed_tools = set(['historical_hemisphere_locator_v2', 'historical_location_finder'])
    forbidden_used = sorted({name for name in tool_names if name and name not in allowed_tools})
    if forbidden_used:
        reasons.append('forbidden tools used: ' + ', '.join(forbidden_used[:5]))
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
