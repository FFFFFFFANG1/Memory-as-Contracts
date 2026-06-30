def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    first = calls[0].get('name','')
    if first != 'historical_leadership_finder':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'first tool was {first}', 'evidence_refs': [{'index': 0, 'name': first}]}
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    has_date = bool(re.search(r'\b(1[5-9]|20)\d{2}\b', resp)) or bool(re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b', resp, re.I))
    # Look for predecessor/successor cues
    low = resp.lower()
    has_pred = 'predecessor' in low or 'preceded' in low or 'previous' in low or 'former' in low
    has_succ = 'successor' in low or 'succeeded' in low or 'replaced' in low or 'next' in low
    if not has_date:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no date found in final response', 'evidence_refs': []}
    if not (has_pred and has_succ):
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'cannot confirm both predecessor and successor named explicitly', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'historical_leadership_finder called first; response includes predecessor/successor cues and a date', 'evidence_refs': []}
