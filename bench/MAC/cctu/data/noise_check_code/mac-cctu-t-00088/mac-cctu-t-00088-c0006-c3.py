def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    word_count = len(response.split())
    if word_count < 400:
        reasons.append('word count {word_count} below 400')
    paragraphs = [part for part in response.split('\n\n') if part.strip()]
    if len(paragraphs) < 2:
        reasons.append('multi-paragraph response missing')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    allowed_tools = set(['landmark_city_locator', 'olympic_history_retriever'])
    forbidden_used = sorted({name for name in tool_names if name and name not in allowed_tools})
    if forbidden_used:
        reasons.append('forbidden tools used: ' + ', '.join(forbidden_used[:5]))
    round_count = len(trajectory)
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
