def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    word_count = len(response.split())
    if word_count == 0:
        reasons.append('response text missing')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_lake_shape_identifier = sum(1 for name in tool_names if name == 'lake_shape_identifier')
    if _count_lake_shape_identifier < 1:
        reasons.append('lake_shape_identifier' + ' call count ' + str(_count_lake_shape_identifier) + ' below 1')
    _count_rare_flower_locator = sum(1 for name in tool_names if name == 'rare_flower_locator')
    if _count_rare_flower_locator < 1:
        reasons.append('rare_flower_locator' + ' call count ' + str(_count_rare_flower_locator) + ' below 1')
    round_count = len(trajectory)
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
