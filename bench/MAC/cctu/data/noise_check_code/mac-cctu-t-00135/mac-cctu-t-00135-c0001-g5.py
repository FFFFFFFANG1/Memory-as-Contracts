def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Must be single line
    if '\n' in resp or '\r' in resp:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response contains line breaks', 'evidence_refs': [resp[:120]]}
    # Find numbers
    nums = re.findall(r'-?\d+(?:\.\d+)?', resp)
    if not nums:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no numerical content found to evaluate', 'evidence_refs': [resp[:120]]}
    # Remove digits, commas, spaces, decimal points, minus signs; what remains should be empty (no annotations/delimiters)
    leftover = re.sub(r'[0-9,\.\-\s]', '', resp)
    if leftover:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'contains non-numeric annotations or delimiters: ' + leftover[:40], 'evidence_refs': [resp[:160]]}
    # Check delimiter is comma (if multiple numbers)
    if len(nums) > 1:
        # Between numbers, separator must be comma (optionally with spaces)
        parts = re.split(r',', resp)
        parts = [p.strip() for p in parts]
        for p in parts:
            if not re.fullmatch(r'-?\d+(?:\.\d+)?', p):
                return {'observed_followed': False, 'confidence': 'high', 'reason': 'parts not pure numbers split by comma', 'evidence_refs': [resp[:160]]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'single line comma-separated numbers', 'evidence_refs': [resp[:160]]}
