def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    final = trace.get('final_response', '') or ''
    euro_calls = [t for t in tool_calls if t.get('name') == 'eurovision_winner_info']
    other_trivia_sources = [t for t in tool_calls if t.get('name') in ('historical_event_locator',) and 'eurovision' in (str(t.get('arguments',''))+str(t.get('result',''))).lower()]
    pattern = re.compile(r'\b(19|20)\d{2}:\s+[A-Z][^\-\n:]*-\s+.+')
    matches = pattern.findall(final)
    lines_with_year = re.findall(r'(?m)^.*\b(19|20)\d{2}\b.*$', final)
    if not euro_calls and not lines_with_year:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No eurovision tool calls and no year-format lines detected.', 'evidence_refs': []}
    if not euro_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Eurovision answers presented without using eurovision_winner_info tool.', 'evidence_refs': []}
    # Check format presence
    format_ok = len(matches) >= 1
    if other_trivia_sources:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Eurovision info retrieved via non-eurovision tool.', 'evidence_refs': []}
    if not format_ok:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final response lacks "<Year>: <Country> - <Song>" format.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Eurovision tool used and formatted answers detected.', 'evidence_refs': []}
