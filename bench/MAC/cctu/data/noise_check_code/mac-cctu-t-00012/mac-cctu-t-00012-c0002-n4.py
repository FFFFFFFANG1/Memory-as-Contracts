def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    _markdown_markers = ('**', '__', '# ')
    _has_markdown = any(mark in response for mark in _markdown_markers)
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    if tool_count < 4:
        reasons.append('tool call count {tool_count} below 4')
    _count_corporate_event_finder = sum(1 for name in tool_names if name == 'corporate_event_finder')
    if _count_corporate_event_finder < 4:
        reasons.append('corporate_event_finder' + ' call count ' + str(_count_corporate_event_finder) + ' below 4')
    _count_historical_event_search = sum(1 for name in tool_names if name == 'historical_event_search')
    if _count_historical_event_search < 4:
        reasons.append('historical_event_search' + ' call count ' + str(_count_historical_event_search) + ' below 4')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
