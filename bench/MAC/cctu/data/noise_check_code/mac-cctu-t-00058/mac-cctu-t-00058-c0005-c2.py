def evaluate(trace):
    import json, re
    resp = trace.get('final_response')
    if resp is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final_response', 'evidence_refs': []}
    text = str(resp)
    stripped = text.strip()
    if not stripped:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final_response', 'evidence_refs': []}
    reasons = []
    # Check valid JSON
    try:
        json.loads(stripped)
        is_json = True
    except Exception as e:
        is_json = False
        reasons.append('final_response is not valid JSON: ' + str(e)[:80])
    # Check markdown code fences
    if '```' in text:
        reasons.append('contains markdown code fence')
    # Check bold/italic markers
    if re.search(r'\*\*[^*]+\*\*', text) or re.search(r'__[^_]+__', text):
        reasons.append('contains bold markdown')
    # Check headings (line starting with #)
    for line in text.splitlines():
        if re.match(r'^\s*#{1,6}\s+\S', line):
            reasons.append('contains markdown heading')
            break
    # Check trailing punctuation on the overall response (outside JSON value)
    # If JSON, trailing char should be } or ] or " or digit etc., not punctuation like . ! ? ; ,
    last = stripped[-1]
    if last in '.!?;,:':
        reasons.append('has trailing punctuation: ' + last)
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'raw JSON with no markdown or trailing punctuation', 'evidence_refs': []}
