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
    _count_legislative_event_tracker = sum(1 for name in tool_names if name == 'legislative_event_tracker')
    if _count_legislative_event_tracker < 3:
        reasons.append('legislative_event_tracker' + ' call count ' + str(_count_legislative_event_tracker) + ' below 3')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
