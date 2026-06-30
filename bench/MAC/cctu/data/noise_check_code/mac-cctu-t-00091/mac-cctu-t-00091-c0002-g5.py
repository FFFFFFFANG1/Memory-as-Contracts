def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    low = text.lower()
    has_counties = bool(re.search(r'count(y|ies)', low))
    has_inst = any(k in low for k in ['institution', 'university', 'college', 'school', 'museum', 'laboratory', 'research'])
    has_features = any(k in low for k in ['feature', 'landmark', 'peak', 'mountain', 'lake', 'river', 'valley', 'falls', 'canyon', 'glacier', 'monument'])
    park_mentions = re.findall(r'park', low)
    structured_signals = text.count('\n-') + text.count('\n*') + text.count('\n#') + text.count(':')
    missing = []
    if not has_counties: missing.append('counties')
    if not has_inst: missing.append('institutions')
    if not has_features: missing.append('features')
    if not park_mentions:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No park content found', 'evidence_refs': []}
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Missing sections: ' + ', '.join(missing), 'evidence_refs': []}
    if structured_signals < 3:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'Response lacks structured profile formatting', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Structured profile includes counties, institutions, and features', 'evidence_refs': []}
