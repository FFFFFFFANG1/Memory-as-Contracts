def evaluate(trace):
    import re
    response = trace.get('final_response')
    if response is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final_response', 'evidence_refs': []}
    text = str(response)
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    reasons = []
    if '```' in text or re.search(r'(^|\n)    \S', text):
        reasons.append('code block detected')
    for line in text.split('\n'):
        s = line.lstrip()
        if re.match(r'^#{1,6}\s', s):
            reasons.append('heading detected')
            break
    for line in text.split('\n'):
        s = line.lstrip()
        if re.match(r'^([-*+]\s+|\d+[\.\)]\s+)', s):
            reasons.append('bullet or numbered list detected')
            break
    if re.search(r'\*\*[^*]+\*\*', text) or re.search(r'__[^_]+__', text):
        reasons.append('bold markdown detected')
    if re.search(r'`[^`]+`', text):
        reasons.append('inline code detected')
    stripped = text.rstrip()
    if stripped and stripped[-1] in '.,;:!?':
        reasons.append('trailing punctuation present: ' + stripped[-1])
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'plain text without headings/lists/code blocks and no trailing punctuation', 'evidence_refs': []}
