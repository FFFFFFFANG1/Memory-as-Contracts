def evaluate(trace):
    import re, json
    resp = trace.get('final_response')
    if resp is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final_response', 'evidence_refs': []}
    text = str(resp)
    stripped = text.strip()
    if not stripped:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    reasons = []
    # Check valid JSON
    is_json = False
    try:
        json.loads(stripped)
        is_json = True
    except Exception as e:
        reasons.append('not valid JSON: ' + str(e)[:80])
    # Check for Markdown code fences
    if '```' in text:
        reasons.append('contains markdown code fence')
    # Check for markdown headings (lines starting with #)
    for line in text.splitlines():
        ls = line.lstrip()
        if ls.startswith('#') and (len(ls) == 1 or ls[1] in '# \t'):
            reasons.append('contains markdown heading')
            break
    # Check for bold/italic markdown markers
    if re.search(r'\*\*[^*]+\*\*', text) or re.search(r'__[^_]+__', text):
        reasons.append('contains bold markdown')
    # Trailing punctuation check - JSON must not end with stray punctuation
    # The last non-whitespace char should be } or ] or " or digit or letter (for true/false/null)
    last = stripped[-1]
    # Allowed JSON terminators
    if last not in ('}', ']', '"') and not last.isalnum():
        reasons.append('trailing punctuation: ' + repr(last))
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    if is_json:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'raw JSON, no markdown/headings/trailing punctuation', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'failed checks', 'evidence_refs': []}
