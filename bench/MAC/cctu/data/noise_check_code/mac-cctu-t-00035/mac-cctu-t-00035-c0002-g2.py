def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    word_count = len(response.split())
    if word_count < 10:
        reasons.append('word count {word_count} below 10')
    if word_count > 30:
        reasons.append('word count {word_count} above 30')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    _count_event_casualty_tracker = sum(1 for name in tool_names if name == 'event_casualty_tracker')
    if _count_event_casualty_tracker > 2:
        reasons.append('event_casualty_tracker' + ' call count ' + str(_count_event_casualty_tracker) + ' above 2')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
