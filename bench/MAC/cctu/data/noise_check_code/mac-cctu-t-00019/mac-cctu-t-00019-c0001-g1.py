def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    if not re.search(r'\b\d{4}-\d{2}-\d{2}\b', response):
        reasons.append('expected date in requested format')
    _markdown_markers = ('**', '__', '# ')
    _has_markdown = any(mark in response for mark in _markdown_markers)
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
