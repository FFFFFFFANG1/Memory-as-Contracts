def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # find numeric counts in the response
    nums = re.findall(r'\b\d+(?:\.\d+)?\b', resp)
    if not nums:
        return {'observed_followed': None,'confidence':'low','reason':'no numeric counts in response','evidence_refs':[]}
    low = resp.lower()
    has_threshold_term = ('threshold' in low) or ('confidence' in low)
    # require a numeric threshold value mentioned alongside the term
    threshold_value = False
    if has_threshold_term:
        for m in re.finditer(r'(threshold|confidence)', low):
            window = low[max(0,m.start()-60):m.end()+60]
            if re.search(r'\d', window):
                threshold_value = True
                break
    followed = has_threshold_term and threshold_value
    reason = ('Counts present with threshold value mentioned' if followed else 'Numeric counts present but confidence threshold not stated with value')
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
