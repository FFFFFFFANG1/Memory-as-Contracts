import re
def evaluate(trace):
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    text = response.strip('\n\r ')
    if '\n' in text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response is not a single line', 'evidence_refs': []}
    m = re.match(r'^Winner:\s+(.+?)\s*$', text)
    if not m:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'does not match "Winner: <name>" pattern', 'evidence_refs': []}
    name = m.group(1)
    if not name.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'missing name after Winner:', 'evidence_refs': []}
    if name[-1] in '.,;:!?':
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'trailing punctuation present', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'matches Winner: <name> single line with no trailing punctuation', 'evidence_refs': []}
