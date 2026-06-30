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
    _count_historical_event_locator = sum(1 for name in tool_names if name == 'historical_event_locator')
    if _count_historical_event_locator < 2:
        reasons.append('historical_event_locator' + ' call count ' + str(_count_historical_event_locator) + ' below 2')
    if not re.search(r'\b\d{4}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', response, flags=re.IGNORECASE):
        reasons.append('date not found in response')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
