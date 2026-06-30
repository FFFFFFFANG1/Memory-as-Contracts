def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '')
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = resp.lower()
    refusal_terms = ['cannot answer', "can't answer", 'unable to answer', 'cannot provide', "can't provide", 'unable to provide', 'i cannot help', 'i am unable', "i'm unable", 'no answer', 'decline to']
    refused = any(t in low for t in refusal_terms)
    has_number = bool(re.search(r'\d', resp))
    flag_terms = ['unverified', 'not verified', 'approximate', 'approximation', 'estimate', 'estimated', 'rough', 'best-effort', 'best effort', 'pre-trained', 'pretrained', 'internal knowledge', 'uncertain', 'may not be accurate', 'not guaranteed', 'caveat', 'caution']
    has_flag = any(t in low for t in flag_terms)
    if refused and not has_number:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response refuses without providing estimate', 'evidence_refs': []}
    if has_number and has_flag:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'numerical estimate provided with unverified flag', 'evidence_refs': []}
    if has_number and not has_flag:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'numerical estimate present but not clearly flagged as unverified', 'evidence_refs': []}
    if not has_number:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no numerical estimate found in response', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'inconclusive', 'evidence_refs': []}
