def evaluate(trace):
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    if 'accession' not in response.lower():
        reasons.append('accession' + ' not mentioned in response')
    if 'provenance' not in response.lower():
        reasons.append('provenance' + ' not mentioned in response')
    if 'exhibit hall' not in response.lower():
        reasons.append('exhibit hall' + ' not mentioned in response')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'rule-based repair checks passed', 'evidence_refs': []}
