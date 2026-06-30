def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    _markdown_markers = ('**', '__', '# ')
    _has_markdown = any(mark in response for mark in _markdown_markers)
    word_count = len(response.split())
    if word_count == 0:
        reasons.append('response text missing')
    paragraphs = [part for part in response.split('\n\n') if part.strip()]
    if len(paragraphs) < 2:
        reasons.append('multi-paragraph response missing')
    tool_names = [str(call.get('name') or '') for call in tool_calls if call.get('name')]
    tool_count = len(tool_names)
    round_count = len(trajectory)
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
