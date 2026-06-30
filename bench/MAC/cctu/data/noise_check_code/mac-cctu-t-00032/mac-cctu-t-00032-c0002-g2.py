def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '').strip()
    if not response:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    reasons = []
    if not response.endswith('.'):
        reasons.append('does not end with a period')
    # exclude trailing period to check internal sentence terminators
    body = response[:-1] if response.endswith('.') else response
    if re.search(r'[.!?]', body):
        reasons.append('contains multiple sentences or non-declarative punctuation')
    if response.rstrip('.').endswith('!') or response.rstrip('.').endswith('?'):
        reasons.append('not declarative (ends with ! or ?)')
    words = response.split()
    if len(words) > 25:
        reasons.append('word count {} exceeds 25'.format(len(words)))
    if len(words) == 0:
        reasons.append('empty response')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': [response[:120]]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'single declarative sentence <=25 words ending with period', 'evidence_refs': [response[:120]]}
