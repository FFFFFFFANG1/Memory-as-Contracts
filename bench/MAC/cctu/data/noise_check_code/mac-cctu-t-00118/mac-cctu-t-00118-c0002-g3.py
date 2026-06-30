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
    if tool_count > 4:
        reasons.append('tool call count {tool_count} above 4')
    _count_historical_event_tool = sum(1 for name in tool_names if name == 'historical_event_tool')
    if _count_historical_event_tool < 2:
        reasons.append('historical_event_tool' + ' call count ' + str(_count_historical_event_tool) + ' below 2')
    if _count_historical_event_tool > 2:
        reasons.append('historical_event_tool' + ' call count ' + str(_count_historical_event_tool) + ' above 2')
    round_count = len(trajectory)
    if round_count > 2:
        reasons.append('interaction rounds {round_count} above 2')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
