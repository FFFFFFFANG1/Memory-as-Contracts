def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response to inspect', 'evidence_refs': []}
    low = response.lower()
    reasons = []
    has_who = 'who' in response and ('mortality' in low)
    if not has_who:
        reasons.append('missing WHO mortality dataset citation')
    has_footnote = ('footnote' in low) or bool(re.search(r'(^|\n)\s*\*+\s', response)) or bool(re.search(r'\[\d+\]', response)) or bool(re.search(r'(^|\n)\s*-{2,}', response))
    if not has_footnote:
        reasons.append('missing footnote section')
    ts_patterns = [
        r'\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?Z?)?\b',
        r'\b\d{2}/\d{2}/\d{4}\b',
        r'\b\d{4}/\d{2}/\d{2}\b',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b',
    ]
    has_timestamp = any(re.search(p, response, re.IGNORECASE) for p in ts_patterns)
    mentions_retrieval = ('retriev' in low) or ('timestamp' in low) or ('accessed' in low) or ('fetched' in low)
    if not has_timestamp:
        reasons.append('missing tool retrieval timestamp/date in footnote')
    if not mentions_retrieval:
        reasons.append('footnote does not reference tool retrieval')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'WHO mortality cited and footnote with retrieval timestamp present', 'evidence_refs': []}
