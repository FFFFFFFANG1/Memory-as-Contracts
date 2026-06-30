def evaluate(trace):
    import re
    resp = trace.get('final_response')
    if resp is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final_response', 'evidence_refs': []}
    text = str(resp)
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    reasons = []
    stripped = text.strip('\n').rstrip()
    if '\n' in stripped or '\r' in stripped:
        reasons.append('contains line breaks (not single line)')
    if len(text) > 280:
        reasons.append(f'length {len(text)} exceeds 280 chars')
    heading_re = re.compile(r'(^|\n)\s{0,3}#{1,6}\s', re.MULTILINE)
    if heading_re.search(text):
        reasons.append('markdown heading detected')
    bullet_re = re.compile(r'(^|\n)\s*([-*+]\s|\d+\.\s)')
    if bullet_re.search(text):
        reasons.append('bullet or numbered list detected')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'single line plain text within 280 chars without headings or bullets', 'evidence_refs': []}
