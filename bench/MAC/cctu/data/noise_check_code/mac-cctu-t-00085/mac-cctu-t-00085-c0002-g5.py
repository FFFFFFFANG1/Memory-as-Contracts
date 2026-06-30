def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    trajectory = trace.get('trajectory') or []
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    _markdown_markers = ('**', '__', '# ')
    _has_markdown = any(mark in response for mark in _markdown_markers)
    word_count = len(response.split())
    if word_count > 150:
        reasons.append('word count {word_count} above 150')
    paragraphs = [part for part in response.split('\n\n') if part.strip()]
    if len(paragraphs) < 2:
        reasons.append('multi-paragraph response missing')
    round_count = len(trajectory)
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
